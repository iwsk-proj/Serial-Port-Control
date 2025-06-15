import tkinter as tk
from tkinter import ttk  
from tkinter import scrolledtext
from tkinter import messagebox
import serial
import serial.tools.list_ports
import threading
import time
import queue 

# --- Stałe ---
BAUD_RATES = [
    150, 300, 600, 1200, 2400, 4800, 9600, 19200,
    38400, 57600, 115200
]
DATA_BITS = [7, 8]
PARITY_OPTIONS = {'N (None)': serial.PARITY_NONE, 'E (Even)': serial.PARITY_EVEN, 'O (Odd)': serial.PARITY_ODD}
STOP_BITS = [1, 2]
FLOW_CONTROL = {
    'None': 'None',
    'RTS/CTS': 'RTS/CTS',
    'DTR/DSR': 'DTR/DSR',
    'XON/XOFF': 'XON/XOFF'
}
TERMINATORS = {
    'None': '',
    'CR (\\r)': '\r',
    'LF (\\n)': '\n',
    'CR+LF (\\r\\n)': '\r\n',
    'Custom': 'Custom'
}

class SerialApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kontrola Portu Szeregowego")
        self.root.geometry("700x800")
        self.root.resizable(False, False)

        self.serial_port = None
        self.receive_thread = None
        self.stop_thread = False
        self.receive_queue = queue.Queue() # Kolejka do odbierania danych z wątku

        # --- GUI Setup ---
        self.create_widgets()
        self.populate_ports()
        self.update_gui_state(connected=False)

        # Okresowe sprawdzanie kolejki odbiorczej
        self.root.after(100, self.process_receive_queue)

    def create_widgets(self):
        # --- Ramka Konfiguracji ---
        config_frame = ttk.LabelFrame(self.root, text="1. Konfiguracja Łącza")
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew", columnspan=3)

        # 1.1 Wybór portu
        ttk.Label(config_frame, text="Port:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.port_combobox = ttk.Combobox(config_frame, width=15)
        self.port_combobox.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        self.refresh_ports_button = ttk.Button(config_frame, text="Odśwież", command=self.populate_ports, width=8)
        self.refresh_ports_button.grid(row=0, column=2, padx=5, pady=2)

        # 1.2 Parametry transmisyjne
        ttk.Label(config_frame, text="Szybkość:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.baud_combobox = ttk.Combobox(config_frame, values=BAUD_RATES, width=15)
        self.baud_combobox.set(9600)
        self.baud_combobox.grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(config_frame, text="Bity danych:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.databits_combobox = ttk.Combobox(config_frame, values=DATA_BITS, width=5)
        self.databits_combobox.set(8)
        self.databits_combobox.grid(row=2, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(config_frame, text="Parzystość:").grid(row=2, column=2, padx=5, pady=2, sticky="w")
        self.parity_combobox = ttk.Combobox(config_frame, values=list(PARITY_OPTIONS.keys()), width=10)
        self.parity_combobox.set('N (None)')
        self.parity_combobox.grid(row=2, column=3, padx=5, pady=2, sticky="w")

        ttk.Label(config_frame, text="Bity stopu:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
        self.stopbits_combobox = ttk.Combobox(config_frame, values=STOP_BITS, width=5)
        self.stopbits_combobox.set(1)
        self.stopbits_combobox.grid(row=3, column=1, padx=5, pady=2, sticky="w")

        # 1.3 Kontrola przepływu
        ttk.Label(config_frame, text="Kontrola przepływu:").grid(row=4, column=0, padx=5, pady=2, sticky="w")
        self.flow_combobox = ttk.Combobox(config_frame, values=list(FLOW_CONTROL.keys()), width=15)
        self.flow_combobox.set('None')
        self.flow_combobox.grid(row=4, column=1, padx=5, pady=2, sticky="ew")

        # 1.5 Wybór terminatora
        ttk.Label(config_frame, text="Terminator:").grid(row=5, column=0, padx=5, pady=2, sticky="w")
        self.terminator_combobox = ttk.Combobox(config_frame, values=list(TERMINATORS.keys()), width=15)
        self.terminator_combobox.set('CR+LF (\\r\\n)')
        self.terminator_combobox.grid(row=5, column=1, padx=5, pady=2, sticky="ew")
        self.terminator_combobox.bind("<<ComboboxSelected>>", self.check_custom_terminator)

        self.custom_terminator_label = ttk.Label(config_frame, text="Własny (1-2 zn):")
        self.custom_terminator_entry = ttk.Entry(config_frame, width=5, state="disabled")
        self.custom_terminator_label.grid(row=5, column=2, padx=5, pady=2, sticky="w")
        self.custom_terminator_entry.grid(row=5, column=3, padx=5, pady=2, sticky="w")


        # Przyciski Połącz/Rozłącz
        self.connect_button = ttk.Button(config_frame, text="Połącz", command=self.toggle_connection)
        self.connect_button.grid(row=6, column=0, columnspan=4, pady=10)

        # --- Ramka Nadawania ---
        send_frame = ttk.LabelFrame(self.root, text="2. Nadawanie (Tryb Tekstowy)")
        send_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew", columnspan=3)
        self.root.grid_rowconfigure(1, weight=1) # Pozwól ramce się rozciągać

        self.send_text = scrolledtext.ScrolledText(send_frame, height=5, wrap=tk.WORD)
        self.send_text.pack(padx=5, pady=5, fill="both", expand=True)

        self.send_button = ttk.Button(send_frame, text="Wyślij", command=self.send_data)
        self.send_button.pack(padx=5, pady=5)

        # --- Ramka Odbioru ---
        receive_frame = ttk.LabelFrame(self.root, text="3. Odbiór (Tryb Tekstowy)")
        receive_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew", columnspan=3)
        self.root.grid_rowconfigure(2, weight=2) # Daj więcej miejsca na odbiór

        self.receive_text = scrolledtext.ScrolledText(receive_frame, height=10, wrap=tk.WORD, state="disabled")
        self.receive_text.pack(padx=5, pady=5, fill="both", expand=True)

        # Przycisk do czyszczenia pola odbioru
        self.clear_button = ttk.Button(receive_frame, text="Wyczyść", command=self.clear_receive_text)
        self.clear_button.pack(padx=5, pady=5)

        # --- Ramka Akcji ---
        action_frame = ttk.LabelFrame(self.root, text="Akcje")
        action_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew", columnspan=3)

        # 5. PING
        self.ping_button = ttk.Button(action_frame, text="5. PING", command=self.perform_ping)
        self.ping_button.grid(row=0, column=0, padx=5, pady=5)

        # --- Status Bar ---
        self.status_bar = ttk.Label(self.root, text="Status: Rozłączony", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=2)

    # --- Funkcje Logiki ---
    def populate_ports(self):
        """Wypełnia listę dostępnych portów szeregowych."""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox['values'] = ports
        if ports:
            self.port_combobox.set(ports[0])
        else:
            self.port_combobox.set("")
            messagebox.showwarning("Brak portów", "Nie znaleziono żadnych portów szeregowych.")

    def check_custom_terminator(self, event=None):
        """Aktywuje/deaktywuje pole własnego terminatora."""
        if self.terminator_combobox.get() == 'Custom':
            self.custom_terminator_entry.config(state="normal")
        else:
            self.custom_terminator_entry.config(state="disabled")
            self.custom_terminator_entry.delete(0, tk.END)

    def get_terminator(self):
        """Pobiera wybrany terminator jako bajty."""
        selected = self.terminator_combobox.get()
        if selected == 'Custom':
            custom = self.custom_terminator_entry.get()
            if 1 <= len(custom) <= 2:
                return custom.encode('utf-8', errors='replace')
            else:
                messagebox.showerror("Błąd terminatora", "Własny terminator musi mieć 1 lub 2 znaki.")
                return None 
        else:
            return TERMINATORS[selected].encode('utf-8', errors='replace')

    def toggle_connection(self):
        """Nawiązuje lub zrywa połączenie szeregowe."""
        if self.serial_port and self.serial_port.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        """Nawiązuje połączenie szeregowe."""
        port_name = self.port_combobox.get()
        if not port_name:
            messagebox.showerror("Błąd", "Wybierz port szeregowy.")
            return

        try:
            baud = int(self.baud_combobox.get())
            data_b = int(self.databits_combobox.get())
            par = PARITY_OPTIONS[self.parity_combobox.get()]
            stop_b = int(self.stopbits_combobox.get())
            flow = self.flow_combobox.get()

            # Konfiguracja kontroli przepływu
            xonxoff = flow == 'XON/XOFF'
            rtscts = flow == 'RTS/CTS'
            dsrdtr = flow == 'DTR/DSR'

            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=baud,
                bytesize=serial.EIGHTBITS if data_b == 8 else serial.SEVENBITS,
                parity=par,
                stopbits=serial.STOPBITS_ONE if stop_b == 1 else serial.STOPBITS_TWO,
                timeout=0.1,  # Krótki timeout do odczytu nieblokującego w wątku
                xonxoff=xonxoff,
                rtscts=rtscts,
                dsrdtr=dsrdtr
            )
            time.sleep(0.5)

            self.status_bar.config(text=f"Status: Połączony z {port_name} ({baud} bps)")
            self.update_gui_state(connected=True)

            # Wątek odbioru
            self.stop_thread = False
            self.receive_thread = threading.Thread(target=self.receive_data_thread, daemon=True)
            self.receive_thread.start()

        except serial.SerialException as e:
            messagebox.showerror("Błąd połączenia", f"Nie można otworzyć portu {port_name}:\n{e}")
            self.serial_port = None
        except ValueError as e:
             messagebox.showerror("Błąd konfiguracji", f"Nieprawidłowa wartość parametru:\n{e}")
             self.serial_port = None
        except Exception as e: # Inne błędy
            messagebox.showerror("Błąd", f"Wystąpił nieoczekiwany błąd:\n{e}")
            self.serial_port = None


    def disconnect(self):
        """Zrywa połączenie szeregowe."""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.stop_thread = True # Sygnał dla wątku do zakończenia
                if self.receive_thread:
                    self.receive_thread.join(timeout=0.5)
                self.serial_port.close()
                self.status_bar.config(text="Status: Rozłączony")
                self.update_gui_state(connected=False)
                self.serial_port = None
            except Exception as e:
                messagebox.showerror("Błąd rozłączania", f"Wystąpił błąd podczas zamykania portu:\n{e}")
        else:
             self.status_bar.config(text="Status: Rozłączony")
             self.update_gui_state(connected=False) 
             self.serial_port = None


    def update_gui_state(self, connected):
        """Aktualizuje stan kontrolek GUI w zależności od stanu połączenia."""
        state = "disabled" if connected else "normal"
        connect_button_text = "Rozłącz" if connected else "Połącz"
        send_state = "normal" if connected else "disabled"

        # Konfiguracja
        self.port_combobox.config(state=state)
        self.refresh_ports_button.config(state=state)
        self.baud_combobox.config(state=state)
        self.databits_combobox.config(state=state)
        self.parity_combobox.config(state=state)
        self.stopbits_combobox.config(state=state)
        self.flow_combobox.config(state=state)
        self.terminator_combobox.config(state=state)

        is_custom = self.terminator_combobox.get() == 'Custom'
        self.custom_terminator_entry.config(state="normal" if not connected and is_custom else "disabled")

        # Przyciski
        self.connect_button.config(text=connect_button_text)
        self.send_button.config(state=send_state)
        self.ping_button.config(state=send_state)

        # Pola tekstowe
        self.send_text.config(state="normal")
        # Czyszczenie pól przy rozłączaniu 
        if not connected:
             self.clear_receive_text()

    def send_data(self):
        """Wysyła dane z pola tekstowego przez port szeregowy."""
        if not (self.serial_port and self.serial_port.is_open):
            messagebox.showwarning("Brak połączenia", "Najpierw połącz się z portem szeregowym.")
            return

        data_to_send_str = self.send_text.get("1.0", tk.END).strip() 
        terminator = self.get_terminator()

        if terminator is None and self.terminator_combobox.get() == 'Custom':
             return 

        try:
            data_to_send_bytes = data_to_send_str.encode('utf-8', errors='replace')
            if terminator:
                data_to_send_bytes += terminator

            self.serial_port.write(data_to_send_bytes)
            self.send_text.delete("1.0", tk.END) 

        except serial.SerialTimeoutException:
            messagebox.showerror("Błąd wysyłania", "Timeout podczas zapisu do portu.")
            self.disconnect() # Rozłącz przy błędzie zapisu
        except Exception as e:
            messagebox.showerror("Błąd wysyłania", f"Wystąpił błąd: {e}")
            self.disconnect()

    def receive_data_thread(self):
        """Wątek do ciągłego odbierania danych z portu szeregowego."""
        while not self.stop_thread and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    # Czytaj dostępne bajty
                    data_bytes = self.serial_port.read(self.serial_port.in_waiting)
                    if data_bytes:
                        # Przekazuje dane do głównego wątku przez kolejkę
                        self.receive_queue.put(data_bytes)
                else:
                    time.sleep(0.05)
                    
            except serial.SerialException:
                # Błąd portu (np. odłączenie urządzenia)
                self.receive_queue.put("SERIAL_ERROR")
                break 
            except Exception:
                 break  

    def process_receive_queue(self):
        """Przetwarza dane odebrane z wątku odbiorczego."""
        try:
            while True: # Przetwórz wszystkie wiadomości w kolejce
                data = self.receive_queue.get_nowait()

                print(f"DEBUG: Odebrano bajty: {repr(data)}")
                
                if data == "SERIAL_ERROR":
                    messagebox.showerror("Błąd portu", "Wystąpił błąd komunikacji z portem szeregowym. Rozłączanie.")
                    self.disconnect()
                elif isinstance(data, bytes):
                     text_data = data.decode('utf-8', errors='replace')
                     self.display_received_data(text_data)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_receive_queue)

    def display_received_data(self, text):
        """Wyświetla odebrany tekst w polu odbioru."""
        self.receive_text.config(state="normal")
        self.receive_text.insert(tk.END, text)
        self.receive_text.see(tk.END) # Przewiń na koniec
        self.receive_text.config(state="disabled")

    def clear_receive_text(self):
        """Czyści pole odbioru."""
        self.receive_text.config(state="normal")
        self.receive_text.delete("1.0", tk.END)
        self.receive_text.config(state="disabled")

    def perform_ping(self):
        """Wysyła PING i mierzy czas odpowiedzi."""
        if not (self.serial_port and self.serial_port.is_open):
            messagebox.showwarning("Brak połączenia", "Najpierw połącz się z portem szeregowym.")
            return

        ping_payload = b"SimplePingRequest_123" 
        timeout = 2.0 # Czas oczekiwania na odpowiedź

        try:
            # Wyczyść bufor odbiorczy przed wysłaniem
            self.serial_port.reset_input_buffer()
            # Wyślij PING
            start_time = time.perf_counter()
            self.serial_port.write(ping_payload)
            self.display_received_data(f"PING >>> {ping_payload.decode('ascii')}\n") # Pokaż co wysłano

            received_bytes = b''
            while time.perf_counter() - start_time < timeout:
                 if self.serial_port.in_waiting > 0:
                     received_bytes += self.serial_port.read(self.serial_port.in_waiting)
                     if ping_payload in received_bytes: # Sprawdź czy odebrano payload
                         end_time = time.perf_counter()
                         rtt = (end_time - start_time) * 1000 # Czas w ms
                         self.display_received_data(f"PONG <<< Otrzymano echo po {rtt:.2f} ms\n")
                         self.status_bar.config(text=f"Status: PING OK ({rtt:.2f} ms)")
                         return # Sukces
                 time.sleep(0.01) 

            # Jeśli pętla się zakończyła bez echa
            self.display_received_data(f"PONG <<< Timeout po {timeout}s\n")
            self.status_bar.config(text="Status: PING Timeout")

        except Exception as e:
            messagebox.showerror("Błąd PING", f"Wystąpił błąd podczas PING: {e}")
            self.disconnect()

    def on_closing(self):
        """Obsługa zamknięcia okna."""
        if self.serial_port and self.serial_port.is_open:
            self.disconnect()
        self.root.destroy()


# --- Główna część programu ---
if __name__ == "__main__":
    main_window = tk.Tk()
    app = SerialApp(main_window)
    main_window.protocol("WM_DELETE_WINDOW", app.on_closing) # Obsługa zamknięcia
    main_window.mainloop()