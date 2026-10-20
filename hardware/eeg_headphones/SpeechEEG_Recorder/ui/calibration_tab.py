"""Calibration Tab — IAPF (quick/full), Productivity baseline, Physiological States baseline."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk


class CalibrationTab(ctk.CTkFrame):
    """Tab for all calibration workflows."""

    def __init__(self, parent, device_manager, calibration_manager):
        super().__init__(parent)
        self._dm = device_manager
        self._cm = calibration_manager

        self._build_ui()
        self._bind_callbacks()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Calibration", font=("", 20, "bold")).pack(pady=(15, 5))

        # === IAPF Section ===
        iapf_frame = ctk.CTkFrame(self)
        iapf_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(iapf_frame, text="IAPF Calibration (Individual Alpha Peak Frequency)",
                     font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(iapf_frame, text="Close your eyes and relax for 30 seconds",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)

        iapf_btn_frame = ctk.CTkFrame(iapf_frame, fg_color="transparent")
        iapf_btn_frame.pack(fill="x", padx=10, pady=10)

        self._iapf_quick_btn = ctk.CTkButton(iapf_btn_frame, text="Quick IAPF (30s)",
                                               command=self._start_quick_iapf)
        self._iapf_quick_btn.pack(side="left", padx=5)

        self._iapf_import_btn = ctk.CTkButton(iapf_btn_frame, text="Import Saved Calibration",
                                                command=self._import_calibration, fg_color="gray")
        self._iapf_import_btn.pack(side="left", padx=5)

        self._iapf_status = ctk.CTkLabel(iapf_frame, text="Status: Not calibrated", font=("", 13))
        self._iapf_status.pack(anchor="w", padx=10, pady=5)

        # IAPF Results
        self._iapf_results_frame = ctk.CTkFrame(iapf_frame, fg_color="transparent")
        self._iapf_results_frame.pack(fill="x", padx=10, pady=5)

        self._iapf_freq_label = ctk.CTkLabel(self._iapf_results_frame, text="IAF: --", font=("", 13))
        self._iapf_freq_label.pack(side="left", padx=15)
        self._iapf_peak_label = ctk.CTkLabel(self._iapf_results_frame, text="Peak Power: --", font=("", 13))
        self._iapf_peak_label.pack(side="left", padx=15)
        self._iapf_bw_label = ctk.CTkLabel(self._iapf_results_frame, text="Bandwidth: --", font=("", 13))
        self._iapf_bw_label.pack(side="left", padx=15)
        self._iapf_band_label = ctk.CTkLabel(self._iapf_results_frame, text="Band: --", font=("", 13))
        self._iapf_band_label.pack(side="left", padx=15)

        # === Productivity Baseline ===
        prod_frame = ctk.CTkFrame(self)
        prod_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(prod_frame, text="Productivity Baseline Calibration",
                     font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(prod_frame, text="Sit quietly with eyes closed while baseline is measured",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)

        prod_btn_frame = ctk.CTkFrame(prod_frame, fg_color="transparent")
        prod_btn_frame.pack(fill="x", padx=10, pady=10)

        self._prod_btn = ctk.CTkButton(prod_btn_frame, text="Start Productivity Baseline",
                                        command=self._start_productivity)
        self._prod_btn.pack(side="left", padx=5)

        self._prod_progress = ctk.CTkProgressBar(prod_frame, width=400)
        self._prod_progress.pack(padx=10, pady=5, fill="x")
        self._prod_progress.set(0)

        self._prod_status = ctk.CTkLabel(prod_frame, text="Status: Not calibrated", font=("", 13))
        self._prod_status.pack(anchor="w", padx=10, pady=5)

        # === Physiological States Baseline ===
        physio_frame = ctk.CTkFrame(self)
        physio_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(physio_frame, text="Physiological States Baseline",
                     font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(physio_frame, text="Sit quietly with eyes closed while baseline is measured",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)

        physio_btn_frame = ctk.CTkFrame(physio_frame, fg_color="transparent")
        physio_btn_frame.pack(fill="x", padx=10, pady=10)

        self._physio_btn = ctk.CTkButton(physio_btn_frame, text="Start Physio Baseline",
                                          command=self._start_physio)
        self._physio_btn.pack(side="left", padx=5)

        self._physio_progress = ctk.CTkProgressBar(physio_frame, width=400)
        self._physio_progress.pack(padx=10, pady=5, fill="x")
        self._physio_progress.set(0)

        self._physio_status = ctk.CTkLabel(physio_frame, text="Status: Not calibrated", font=("", 13))
        self._physio_status.pack(anchor="w", padx=10, pady=5)

        # === Save calibration ===
        save_frame = ctk.CTkFrame(self)
        save_frame.pack(fill="x", padx=20, pady=10)

        self._save_btn = ctk.CTkButton(save_frame, text="Save All Calibration Data",
                                        command=self._save_calibration)
        self._save_btn.pack(side="left", padx=10, pady=10)

        self._save_status = ctk.CTkLabel(save_frame, text="", font=("", 12))
        self._save_status.pack(side="left", padx=10, pady=10)

    def _bind_callbacks(self):
        self._cm.on_iapf_done = self._on_iapf_done
        self._cm.on_iapf_failed = self._on_iapf_failed
        self._cm.on_productivity_progress = self._on_prod_progress
        self._cm.on_productivity_done = self._on_prod_done
        self._cm.on_physio_progress = self._on_physio_progress
        self._cm.on_physio_done = self._on_physio_done

    def _start_quick_iapf(self):
        if not self._dm.is_connected:
            messagebox.showwarning("Not Connected", "Connect to a device first.")
            return
        self._iapf_quick_btn.configure(state="disabled")
        self._iapf_status.configure(text="Status: Calibrating... Close your eyes (30s)", text_color="orange")
        # Ensure device is streaming (should already be from connection)
        if not self._dm.is_streaming:
            self._dm.start_signal()
        self._cm.start_quick_iapf()

    def _start_productivity(self):
        if not self._dm.is_connected:
            messagebox.showwarning("Not Connected", "Connect to a device first.")
            return
        self._prod_btn.configure(state="disabled")
        self._prod_status.configure(text="Status: Calibrating... Stay still", text_color="orange")
        self._dm.start_signal()
        self._cm.start_productivity_baseline()

    def _start_physio(self):
        if not self._dm.is_connected:
            messagebox.showwarning("Not Connected", "Connect to a device first.")
            return
        self._physio_btn.configure(state="disabled")
        self._physio_status.configure(text="Status: Calibrating... Stay still", text_color="orange")
        self._dm.start_signal()
        self._cm.start_physio_baseline()

    def _import_calibration(self):
        filepath = filedialog.askopenfilename(
            title="Select Calibration File",
            filetypes=[("JSON files", "*.json")],
            initialdir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        )
        if not filepath:
            return

        data = self._cm.load_calibration(filepath)
        if not data:
            messagebox.showerror("Error", "Failed to load calibration file")
            return

        imported = 0
        if data.get("iapf") and self._dm.is_connected:
            if self._cm.import_iapf(data["iapf"]):
                self._show_iapf_results(data["iapf"])
                imported += 1

        if data.get("productivity_baselines") and self._dm.is_connected:
            if self._cm.import_productivity_baselines(data["productivity_baselines"]):
                self._prod_status.configure(text="Status: Imported", text_color="green")
                imported += 1

        if data.get("physio_baselines") and self._dm.is_connected:
            if self._cm.import_physio_baselines(data["physio_baselines"]):
                self._physio_status.configure(text="Status: Imported", text_color="green")
                imported += 1

        messagebox.showinfo("Import", f"Imported {imported} calibration(s) from file")

    def _save_calibration(self):
        filepath = filedialog.asksaveasfilename(
            title="Save Calibration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        )
        if filepath:
            self._cm.save_calibration(filepath)
            self._save_status.configure(text="Saved!", text_color="green")

    # --- Callbacks from calibration manager (SDK thread) ---

    def _on_iapf_done(self, data):
        self.after(0, lambda: self._show_iapf_results(data))

    def _show_iapf_results(self, data):
        self._iapf_quick_btn.configure(state="normal")
        self._iapf_status.configure(text="Status: Calibrated", text_color="green")
        self._iapf_freq_label.configure(text=f"IAF: {data['individualFrequency']:.2f} Hz")
        self._iapf_peak_label.configure(text=f"Peak Power: {data['individualPeakFrequencyPower']:.3f}")
        self._iapf_bw_label.configure(text=f"Bandwidth: {data['individualBandwidth']:.2f} Hz")
        self._iapf_band_label.configure(
            text=f"Band: {data['lowerFrequency']:.1f} - {data['upperFrequency']:.1f} Hz")

    def _on_iapf_failed(self, reason):
        self.after(0, lambda: self._show_iapf_failed(reason))

    def _show_iapf_failed(self, reason):
        self._iapf_quick_btn.configure(state="normal")
        self._iapf_status.configure(text=f"Status: Failed - {reason}", text_color="red")

    def _on_prod_progress(self, progress):
        self.after(0, lambda p=progress: self._prod_progress.set(p))

    def _on_prod_done(self, data):
        self.after(0, lambda: self._show_prod_done(data))

    def _show_prod_done(self, data):
        self._prod_btn.configure(state="normal")
        self._prod_progress.set(1.0)
        self._prod_status.configure(text="Status: Calibrated", text_color="green")

    def _on_physio_progress(self, progress):
        self.after(0, lambda p=progress: self._physio_progress.set(p))

    def _on_physio_done(self, data):
        self.after(0, lambda: self._show_physio_done(data))

    def _show_physio_done(self, data):
        self._physio_btn.configure(state="normal")
        self._physio_progress.set(1.0)
        self._physio_status.configure(text="Status: Calibrated", text_color="green")
