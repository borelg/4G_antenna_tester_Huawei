import time
import csv
from datetime import datetime

import tkinter as tk
from tkinter import ttk

# Matplotlib for plotting
import matplotlib
matplotlib.use("TkAgg")  # Use TkAgg backend for embedding in Tkinter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection

# CSV file to store signal data
CSV_FILENAME = 'signal_data.csv'

def parse_signal_value(value_str):
    """
    Convert a string like '-110dBm' or '-14.0dB' to a float (e.g., -110 or -14.0).
    Returns None if parsing fails or empty string.
    """
    if not value_str:
        return None
    try:
        # Remove potential suffixes like 'dBm', 'dB', etc.
        cleaned = value_str.lower().replace('dbm', '').replace('db', '').strip()
        return float(cleaned)
    except ValueError:
        return None

class SignalMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("4G Antenna Signal Monitor")
        
        # Variables to hold user input (IP & password)
        self.ip_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.router_url = None  # Will be constructed after user clicks connect

        # Store data for plotting
        self.time_points = []
        self.rsrp_values = []
        self.rsrq_values = []
        self.rssi_values = []
        self.sinr_values = []
        
        # Sample index (used as x-axis for plots)
        self.sample_index = 0
        # Limit how many data points we keep in memory/plot
        self.max_points = 50
        
        # -----------------------------
        # CREATE UI: CONNECTION FRAME
        # -----------------------------
        self.connection_frame = ttk.Frame(self.root)
        self.connection_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # IP address label & entry
        tk.Label(self.connection_frame, text="Router IP:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.ip_entry = tk.Entry(self.connection_frame, textvariable=self.ip_var, width=15)
        self.ip_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Password label & entry
        tk.Label(self.connection_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.password_entry = tk.Entry(self.connection_frame, textvariable=self.password_var, width=15, show="*")
        self.password_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Connect button
        self.connect_button = tk.Button(self.connection_frame, text="Connect", command=self.connect_to_router)
        self.connect_button.grid(row=0, column=2, rowspan=2, sticky=tk.NS, padx=10, pady=2)
        
        # -----------------------------
        # CREATE UI: DISPLAY & PLOTS
        # -----------------------------
        # Frame for textual info (top)
        self.info_frame = ttk.Frame(self.root)
        self.info_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False)
        
        # Label to show textual info about signal
        self.info_label = tk.Label(self.info_frame, text="Please enter IP & password, then click Connect.", 
                                   font=("Arial", 12), justify="left")
        self.info_label.pack(padx=10, pady=5)
        
        # Frame for Matplotlib figure (bottom)
        self.plot_frame = ttk.Frame(self.root)
        self.plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        # Create the matplotlib Figure and subplots
        self.fig = Figure(figsize=(8, 6), dpi=100)
        
        # Four subplots for RSRP, RSRQ, RSSI, SINR
        self.ax_rsrp = self.fig.add_subplot(221)
        self.ax_rsrq = self.fig.add_subplot(222)
        self.ax_rssi = self.fig.add_subplot(223)
        self.ax_sinr = self.fig.add_subplot(224)
        
        # Initialize lines (empty for now)
        self.rsrp_line, = self.ax_rsrp.plot([], [], 'r-', label="RSRP (dBm)")
        self.rsrq_line, = self.ax_rsrq.plot([], [], 'g-', label="RSRQ (dB)")
        self.rssi_line, = self.ax_rssi.plot([], [], 'b-', label="RSSI (dBm)")
        self.sinr_line, = self.ax_sinr.plot([], [], 'm-', label="SINR (dB)")
        
        # Set titles/labels for each subplot
        self.ax_rsrp.set_title("RSRP")
        self.ax_rsrq.set_title("RSRQ")
        self.ax_rssi.set_title("RSSI")
        self.ax_sinr.set_title("SINR")
        
        for ax in [self.ax_rsrp, self.ax_rsrq, self.ax_rssi, self.ax_sinr]:
            ax.set_xlabel("Sample #")
            ax.set_ylabel("Value")
            ax.legend(loc="upper right")
            ax.grid(True)
        
        # Embed the figure in Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Create CSV headers if needed
        self.setup_csv()

    def setup_csv(self):
        """
        Creates a CSV file with headers if the file doesn't exist yet.
        """
        try:
            with open(CSV_FILENAME, 'r', newline='') as _:
                # If file exists, do nothing
                pass
        except FileNotFoundError:
            with open(CSV_FILENAME, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp",
                    "RSRP (dBm)",
                    "RSRQ (dB)",
                    "RSSI (dBm)",
                    "SINR (dB)",
                    "PCI",
                    "Cell ID",
                    "Band",
                    "DL Bandwidth",
                    "UL Bandwidth",
                ])

    def connect_to_router(self):
        """
        Read user input (IP & password), build the router URL, 
        and start the periodic update.
        """
        ip = self.ip_var.get().strip()
        password = self.password_var.get().strip()

        if not ip or not password:
            self.info_label.config(text="Please enter both IP and password.")
            return

        # Build the router URL (assuming default username 'admin')
        self.router_url = f"http://admin:{password}@{ip}/"

        # Update the info label to show we are attempting connection
        self.info_label.config(text="Attempting connection...")

        # Start periodic updates
        self.update_signal_data()

    def update_signal_data(self):
        """
        Fetch the signal metrics from the router and:
          1. Update the text UI (Tkinter Label).
          2. Append a row to the CSV file.
          3. Update the data lists for plotting and redraw the charts.
          4. Schedule the next update in 2 seconds.
        """
        if not self.router_url:
            # If for some reason update is called but we haven't connected
            return

        try:
            # Connect to the router
            with Connection(self.router_url) as connection:
                client = Client(connection)
                
                # Retrieve signal data
                signal_data = client.device.signal()
                
                # Extract fields
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                rsrp_str = signal_data.get('rsrp', '')
                rsrq_str = signal_data.get('rsrq', '')
                rssi_str = signal_data.get('rssi', '')
                sinr_str = signal_data.get('sinr', '')
                pci = signal_data.get('pci', '')
                cell_id = signal_data.get('cell_id', '')
                band = signal_data.get('band', '')
                dl_bw = signal_data.get('dlbandwidth', '')
                ul_bw = signal_data.get('ulbandwidth', '')
                
                # Convert to floats for plotting
                rsrp_val = parse_signal_value(rsrp_str)   # '-110dBm' -> -110
                rsrq_val = parse_signal_value(rsrq_str)   # '-14.0dB' -> -14.0
                rssi_val = parse_signal_value(rssi_str)   # '-77dBm'  -> -77
                sinr_val = parse_signal_value(sinr_str)   # '0dB'     -> 0
                
                # Update UI label text
                info_text = (
                    f"Timestamp: {timestamp}\n"
                    f"RSRP: {rsrp_str}\n"
                    f"RSRQ: {rsrq_str}\n"
                    f"RSSI: {rssi_str}\n"
                    f"SINR: {sinr_str}\n"
                    f"PCI: {pci}\n"
                    f"Cell ID: {cell_id}\n"
                    f"Band: {band}\n"
                    f"DL Bandwidth: {dl_bw}\n"
                    f"UL Bandwidth: {ul_bw}\n"
                )
                self.info_label.config(text=info_text)
                
                # Write to CSV file
                with open(CSV_FILENAME, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        timestamp,
                        rsrp_str,
                        rsrq_str,
                        rssi_str,
                        sinr_str,
                        pci,
                        cell_id,
                        band,
                        dl_bw,
                        ul_bw
                    ])
                
                # Update plotting data
                self.sample_index += 1
                self.rsrp_values.append(rsrp_val)
                self.rsrq_values.append(rsrq_val)
                self.rssi_values.append(rssi_val)
                self.sinr_values.append(sinr_val)
                self.time_points.append(self.sample_index)
                
                # Keep lists from growing too large
                if len(self.time_points) > self.max_points:
                    self.time_points.pop(0)
                    self.rsrp_values.pop(0)
                    self.rsrq_values.pop(0)
                    self.rssi_values.pop(0)
                    self.sinr_values.pop(0)
                
                # Update plots
                import numpy as np
                rsrp_plot = np.ma.masked_where([v is None for v in self.rsrp_values], self.rsrp_values)
                rsrq_plot = np.ma.masked_where([v is None for v in self.rsrq_values], self.rsrq_values)
                rssi_plot = np.ma.masked_where([v is None for v in self.rssi_values], self.rssi_values)
                sinr_plot = np.ma.masked_where([v is None for v in self.sinr_values], self.sinr_values)
                
                self.rsrp_line.set_xdata(self.time_points)
                self.rsrp_line.set_ydata(rsrp_plot)
                self.ax_rsrp.relim()
                self.ax_rsrp.autoscale_view()
                
                self.rsrq_line.set_xdata(self.time_points)
                self.rsrq_line.set_ydata(rsrq_plot)
                self.ax_rsrq.relim()
                self.ax_rsrq.autoscale_view()
                
                self.rssi_line.set_xdata(self.time_points)
                self.rssi_line.set_ydata(rssi_plot)
                self.ax_rssi.relim()
                self.ax_rssi.autoscale_view()
                
                self.sinr_line.set_xdata(self.time_points)
                self.sinr_line.set_ydata(sinr_plot)
                self.ax_sinr.relim()
                self.ax_sinr.autoscale_view()
                
                self.canvas.draw()
                
        except Exception as e:
            # If there's an error (connection issues, etc.), show it in UI
            self.info_label.config(text=f"Error:\n{e}")

        # Schedule the next update in 2000 ms (2 seconds)
        self.root.after(2000, self.update_signal_data)

def main():
    root = tk.Tk()
    app = SignalMonitorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
