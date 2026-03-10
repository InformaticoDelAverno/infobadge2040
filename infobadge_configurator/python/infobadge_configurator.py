import tkinter as tk
from tkinter import ttk, messagebox
from serial import Serial, SerialException
import serial.tools.list_ports
from PIL import Image, ImageTk
import os


class SerialApp:
    def __init__(self, root):
        self.root = root
        self.root.title("InfoBadge2040 Configurator")
        self.root.configure(bg="#6acf65")
        self.root.geometry("500x600")
        self.serial_port = None

        self.setup_ui()

    def setup_ui(self):
        # Logo
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(base_path, "thebadges_logo.png")

            logo = Image.open(logo_path)
            # logo = logo.resize((200, 60), Image.Resampling.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(logo)
            logo_label = tk.Label(self.root, image=self.logo_img, bg="#6acf65")
            logo_label.pack(pady=10)
        except Exception as e:
            print("Error cargando el logo:", e)

        # Campos de entrada
        self.entries = {}
        labels = ["Name", "Position", "Webpage", "X account", "QR URL"]
        for label in labels:
            lbl = tk.Label(self.root, text=label, bg="#6acf65", fg="#046307", font=("Arial", 16, "bold"))
            lbl.pack()
            entry = tk.Entry(self.root, bg="#ffffff", fg="#046307", insertbackground="#000000", width=50)
            entry.pack(pady=5)
            self.entries[label] = entry

        # Selector de puerto serie
        port_label = tk.Label(self.root, text="Serial Port", bg="#6acf65", fg="#046307", font=("Arial", 16, "bold"))
        port_label.pack(pady=(20, 5))

        self.port_selector = ttk.Combobox(self.root, values=self.get_serial_ports(), width=50)
        self.port_selector.pack()

        # Botón de envío
        send_btn = tk.Button(self.root, text="Send Data", command=self.send_data,
                            bg="#000000", fg="#6acf65", font=("Arial", 10, "bold"), padx=10, pady=5)
        send_btn.pack(pady=20)

    def get_serial_ports(self):
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def send_data(self):
        port = self.port_selector.get()
        if not port:
            messagebox.showerror("Error", "Please select a serial port.")
            return

        try:
            with Serial(port, 9600, timeout=1) as ser:
                for label, entry in self.entries.items():
                    text = entry.get()
                    ser.write((text + '\n').encode('utf-8'))
            messagebox.showinfo("Success", "Data sent successfully.")
        except SerialException as e:
            messagebox.showerror("Serial Error", str(e))

# Iniciar app
if __name__ == "__main__":
    root = tk.Tk()
    app = SerialApp(root)
    root.mainloop()
