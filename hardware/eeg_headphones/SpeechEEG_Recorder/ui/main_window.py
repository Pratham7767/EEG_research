"""Main Window — tabbed GUI shell tying all tabs together."""
import customtkinter as ctk
from ui.connection_tab import ConnectionTab
from ui.resistance_tab import ResistanceTab
from ui.calibration_tab import CalibrationTab
from ui.recording_tab import RecordingTab


class MainWindow(ctk.CTk):
    """Main application window with tabbed navigation."""

    def __init__(self, device_manager, calibration_manager, recording_engine, trial_manager, export_manager):
        super().__init__()

        self._dm = device_manager
        self._cm = calibration_manager
        self._engine = recording_engine
        self._tm = trial_manager
        self._export = export_manager

        self.title("Speech + EEG Recorder")
        self.geometry("1100x850")
        self.minsize(900, 700)

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()

        # SDK update loop
        self._schedule_sdk_update()

        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=50)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="Speech + EEG Recorder", font=("", 22, "bold")).pack(side="left", padx=20)

        self._status_dot = ctk.CTkLabel(header, text="", font=("", 14), width=20)
        self._status_dot.pack(side="right", padx=5)
        self._header_status = ctk.CTkLabel(header, text="Disconnected", font=("", 13))
        self._header_status.pack(side="right", padx=10)

        # Tabview — 4 tabs (Live EEG is now merged into Record)
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=10, pady=10)

        tab1 = self._tabview.add("1. Connect")
        tab2 = self._tabview.add("2. Resistance")
        tab3 = self._tabview.add("3. Calibrate")
        tab4 = self._tabview.add("4. Record + Monitor")

        # Instantiate tab content
        self._conn_tab = ConnectionTab(tab1, self._dm)
        self._conn_tab.pack(fill="both", expand=True)

        self._resist_tab = ResistanceTab(tab2, self._dm, tabview=self._tabview)
        self._resist_tab.pack(fill="both", expand=True)

        self._cal_tab = CalibrationTab(tab3, self._dm, self._cm)
        self._cal_tab.pack(fill="both", expand=True)

        self._rec_tab = RecordingTab(tab4, self._dm, self._engine, self._tm, self._export, self._cm)
        self._rec_tab.pack(fill="both", expand=True)

        # Subscribe to connection events via event bus (no overwrite)
        self._dm.events.subscribe("connection",
            lambda connected, msg: self.after(0, lambda: self._update_header(connected, msg)))
        self._dm.events.subscribe("battery",
            lambda charge: self.after(0, lambda: self._header_status.configure(
                text=f"Connected | Battery: {charge}%", text_color="green")))

    def _update_header(self, connected, msg):
        if connected:
            self._header_status.configure(text=f"Connected | Battery: {self._dm.battery}%", text_color="green")
            self._status_dot.configure(text="●", text_color="green")
        else:
            self._header_status.configure(text=msg, text_color="orange")
            self._status_dot.configure(text="●", text_color="red")

    def _schedule_sdk_update(self):
        """Periodically call locator.update() for SDK event processing."""
        self._dm.update()
        self.after(20, self._schedule_sdk_update)

    def _on_close(self):
        try:
            # Clean up recording tab (unsubscribes events, stops graphs)
            if hasattr(self, '_rec_tab'):
                self._rec_tab.destroy()
        except Exception:
            pass
        try:
            # Stop recording if active
            if self._engine.is_recording:
                self._engine.stop()
        except Exception:
            pass
        try:
            # Disconnect device
            self._dm.disconnect()
        except Exception:
            pass
        self.destroy()
