"""Connection Tab — device scanning, selection, and connection with retry status."""
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk


class ConnectionTab(ctk.CTkFrame):
    """Tab for device discovery and connection."""

    def __init__(self, parent, device_manager):
        super().__init__(parent)
        self._dm = device_manager
        self._devices = []

        self._build_ui()
        self._bind_callbacks()

    def _build_ui(self):
        # Title
        ctk.CTkLabel(self, text="Device Connection", font=("", 20, "bold")).pack(pady=(15, 5))

        # Scan section
        scan_frame = ctk.CTkFrame(self)
        scan_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(scan_frame, text="Search Time (s):").grid(row=0, column=0, padx=10, pady=10)
        self._search_time = ctk.CTkEntry(scan_frame, width=60)
        self._search_time.insert(0, "10")
        self._search_time.grid(row=0, column=1, padx=5, pady=10)

        self._scan_btn = ctk.CTkButton(scan_frame, text="Scan for Headphones", command=self._on_scan)
        self._scan_btn.grid(row=0, column=2, padx=20, pady=10)

        self._scan_status = ctk.CTkLabel(scan_frame, text="")
        self._scan_status.grid(row=0, column=3, padx=10, pady=10)

        # Device list
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(list_frame, text="Found Devices:", font=("", 14)).pack(anchor="w", padx=10, pady=5)

        # Treeview for device list
        tree_frame = tk.Frame(list_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._tree = ttk.Treeview(tree_frame, columns=("name", "serial", "type"), show="headings", height=5)
        self._tree.heading("name", text="Name")
        self._tree.heading("serial", text="Serial")
        self._tree.heading("type", text="Type")
        self._tree.column("name", width=200)
        self._tree.column("serial", width=200)
        self._tree.column("type", width=100)
        self._tree.pack(fill="both", expand=True)

        # Connect button
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=20, pady=10)

        self._connect_btn = ctk.CTkButton(btn_frame, text="Connect", command=self._on_connect, state="disabled")
        self._connect_btn.pack(side="left", padx=10)

        self._disconnect_btn = ctk.CTkButton(btn_frame, text="Disconnect", command=self._on_disconnect, state="disabled",
                                               fg_color="gray")
        self._disconnect_btn.pack(side="left", padx=10)

        # Connection status
        status_frame = ctk.CTkFrame(self)
        status_frame.pack(fill="x", padx=20, pady=10)

        self._conn_status_label = ctk.CTkLabel(status_frame, text="Status: Not connected", font=("", 14))
        self._conn_status_label.pack(side="left", padx=10, pady=10)

        self._battery_label = ctk.CTkLabel(status_frame, text="Battery: --", font=("", 14))
        self._battery_label.pack(side="right", padx=10, pady=10)

    def _bind_callbacks(self):
        # Use event bus — no overwrites, multiple tabs can listen
        self._dm.events.subscribe("device_list", self._on_device_list)
        self._dm.events.subscribe("connection", self._on_connection_changed)
        self._dm.events.subscribe("battery", self._on_battery_update)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _on_scan(self):
        self._scan_btn.configure(state="disabled")
        self._scan_status.configure(text="Scanning...")
        self._tree.delete(*self._tree.get_children())
        self._devices = []

        try:
            search_time = int(self._search_time.get())
        except ValueError:
            search_time = 10

        self._dm.scan_devices(search_time)

    def _on_device_list(self, devices):
        """Called from SDK thread — schedule UI update."""
        self._devices = devices
        self.after(0, self._update_device_list)

    def _update_device_list(self):
        self._tree.delete(*self._tree.get_children())
        for d in self._devices:
            self._tree.insert("", "end", values=(d["name"], d["serial"], d["type"]))

        self._scan_btn.configure(state="normal")
        count = len(self._devices)
        self._scan_status.configure(text=f"Found {count} device(s)")

    def _on_tree_select(self, event):
        selection = self._tree.selection()
        self._connect_btn.configure(state="normal" if selection else "disabled")

    def _on_connect(self):
        selection = self._tree.selection()
        if not selection:
            return
        values = self._tree.item(selection[0])["values"]
        serial = str(values[1])

        self._connect_btn.configure(state="disabled")
        self._conn_status_label.configure(text="Status: Connecting...")
        self._dm.connect(serial, bipolar=True)

    def _on_disconnect(self):
        self._dm.disconnect()

    def _on_connection_changed(self, connected, message):
        """Called from SDK thread."""
        self.after(0, lambda: self._update_connection_ui(connected, message))

    def _update_connection_ui(self, connected, message):
        if connected:
            self._conn_status_label.configure(text=f"Status: Connected", text_color="green")
            self._connect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="normal")
            # Update battery
            self._battery_label.configure(text=f"Battery: {self._dm.battery}%")
        else:
            self._conn_status_label.configure(text=f"Status: {message}", text_color="red" if "failed" in message.lower() else "orange")
            self._connect_btn.configure(state="normal")
            self._disconnect_btn.configure(state="disabled")

    def _on_battery_update(self, charge):
        self.after(0, lambda: self._battery_label.configure(text=f"Battery: {charge}%"))
