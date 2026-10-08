"""Beamline gas handling and temperature program interface."""

import logging
import re
import time as ttime
from importlib.resources import as_file, files
from pathlib import Path

import bluesky.plan_stubs as bps
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
)
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtGui, QtWidgets, uic

from iss_xsample.data import pad_setpoints, program_dataframe
from iss_xsample.polling import ArchiverPoller

logger = logging.getLogger(__name__)
with as_file(files("iss_xsample").joinpath("ui/xsample_new.ui")) as ui_path:
    _UiForm, _UiBase = uic.loadUiType(str(ui_path))


def message_box(title, message):
    return QtWidgets.QMessageBox.information(None, title, message)


def update_figure(axes, toolbar, canvas):
    """Clear plots without an extra synchronous render before new data arrives."""
    for axis in axes:
        axis.clear()
    toolbar.update()


class XsampleGui(_UiForm, _UiBase):
    def __init__(
        self,
        gas_cart=None,
        mobile_gh_system=None,
        total_flow_meter=None,
        rga_channels=None,
        rga_masses=None,
        heater_enable1=None,
        ghs=None,
        switch_manifold=None,
        RE=None,
        archiver=None,
        sample_envs_dict=None,
        reset_rga=None,
        flow_condition_valves=None,
        pdu=None,
        *args,
        **kwargs,
    ):

        super().__init__(*args, **kwargs)

        required = {
            "gas_cart": gas_cart,
            "ghs": ghs,
            "switch_manifold": switch_manifold,
            "RE": RE,
            "archiver": archiver,
            "sample_envs_dict": sample_envs_dict,
            "total_flow_meter": total_flow_meter,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError("Missing beamline configuration: " + ", ".join(missing))
        if not sample_envs_dict:
            raise ValueError(
                "sample_envs_dict must contain at least one sample environment"
            )
        self.setupUi(self)
        self.addCanvas()
        self.gas_cart = gas_cart
        self.total_flow_meter = total_flow_meter
        self.rga_channels = [] if rga_channels is None else rga_channels
        self.rga_masses = [] if rga_masses is None else rga_masses
        self.ghs = ghs
        self.mobile_gh_system = mobile_gh_system
        self.switch_manifold = switch_manifold
        if reset_rga is not None:
            self.reset_rga = reset_rga
        self.flow_condition_valves = flow_condition_valves
        self.pdu = pdu

        self.sample_envs_dict = sample_envs_dict

        self.RE = RE
        self._df_ = None
        self.archiver = archiver

        self.num_steps = 30
        self.step_priority = np.zeros(self.num_steps)

        self.push_clear_program.clicked.connect(self.clear_program)
        self.push_start_program.clicked.connect(self.start_program)
        self.push_pause_program.setChecked(0)
        self.push_pause_program.toggled.connect(self.pause_program)
        self.push_stop_program.clicked.connect(self.stop_program)
        self.pushButton_reset_cart.clicked.connect(self.reset_cart_plc)
        self.pushButton_switch.clicked.connect(self.switch_gases)

        self.pushButton_reset_rga.clicked.connect(self.reset_rga)
        self.pushButton_vacuum_off.clicked.connect(self.set_vacuum_pump_off)
        self.pushButton_vacuum_on.clicked.connect(self.set_vacuum_pump_on)

        self.process_program = None
        self.plot_program_flag = False
        self.program_plot_moving_flag = True
        self._plot_temp_program = None

        sample_envs_list = list(self.sample_envs_dict)
        self.comboBox_sample_envs.addItems(sample_envs_list)
        self.comboBox_sample_envs.currentIndexChanged.connect(self.sample_env_selected)
        self.sample_env_selected()

        # Switching manifold

        for element, valve in self.switch_manifold.items():
            button = getattr(self, f"radioButton_switch_{element}_{valve.direction}")
            button.setChecked(True)

        switching_buttons = [
            self.radioButton_switch_ghs_ch1_reactor,
            self.radioButton_switch_ghs_ch2_reactor,
            self.radioButton_switch_cart_reactor,
            self.radioButton_switch_ghs_ch1_exhaust,
            self.radioButton_switch_ghs_ch2_exhaust,
            self.radioButton_switch_cart_exhaust,
        ]

        for button in switching_buttons:
            button.clicked.connect(self.actuate_switching_valve)

        condition_valves_buttons = []
        for i in range(1, 5):
            string_close = f"radioButton_valve{i}_close"
            string_open = f"radioButton_valve{i}_open"
            condition_valves_buttons.append(getattr(self, string_open))
            condition_valves_buttons.append(getattr(self, string_close))

        for button in condition_valves_buttons:
            button.clicked.connect(self.actuate_condition_valves)

        self.gas_mapper = {
            "1": {0: 0, 4: 1, 2: 4, 3: 2, 1: 3},
            "2": {0: 0, 2: 1, 3: 2},
            "3": {0: 0, 1: 1, 2: 2},
            "4": {0: 0, 1: 2, 2: 1},
            "5": {0: 0, 1: 1, 2: 2},
        }

        for indx in range(8):
            getattr(self, f"checkBox_rga{indx + 1}").toggled.connect(self.update_status)

        for indx, rga_mass in enumerate(self.rga_masses):
            getattr(self, f"spinBox_rga_mass{indx + 1}").setValue(rga_mass.get())
            getattr(self, f"spinBox_rga_mass{indx + 1}").valueChanged.connect(
                self.change_rga_mass
            )

        # initializing mobile cart MFC readings

        for indx_mfc in range(4):
            mfc_widget = getattr(self, f"spinBox_cart_mfc{indx_mfc + 1}_sp")
            mfc_widget.setValue(self.gas_cart[indx_mfc + 1]["mfc"].sp.get())
            mfc_widget.editingFinished.connect(self.set_mfc_cart_flow)

        for index in range(1, 4):
            getattr(self, f"checkBox_cart_vlv{index}").toggled.connect(
                self.toggle_cart_valve
            )

        for indx_ch in range(2):
            ch = f"{indx_ch + 1}"

            # setting outlets
            for outlet in ["reactor", "exhaust"]:
                rb_outlet = getattr(self, f"radioButton_ch{indx_ch + 1}_{outlet}")
                if self.ghs["channels"][f"{indx_ch + 1}"][outlet].get():
                    rb_outlet.setChecked(True)
                else:
                    rb_outlet.setChecked(False)

            getattr(self, f"radioButton_ch{indx_ch + 1}_reactor").toggled.connect(
                self.toggle_exhaust_reactor
            )
            getattr(self, f"radioButton_ch{indx_ch + 1}_exhaust").toggled.connect(
                self.toggle_exhaust_reactor
            )

            getattr(self, f"radioButton_ch{indx_ch + 1}_bypass1").toggled.connect(
                self.toggle_bypass_bubbler
            )
            getattr(self, f"radioButton_ch{indx_ch + 1}_bypass2").toggled.connect(
                self.toggle_bypass_bubbler
            )

            getattr(self, f"radioButton_ch{indx_ch + 1}_bubbler1").toggled.connect(
                self.toggle_bypass_bubbler
            )
            getattr(self, f"radioButton_ch{indx_ch + 1}_bubbler2").toggled.connect(
                self.toggle_bypass_bubbler
            )

            # set signal handling of gas selector widgets
            for indx_mnf in range(5):
                gas_selector_widget = getattr(
                    self, f"comboBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_gas"
                )
                gas = self.ghs["manifolds"][f"{indx_mnf + 1}"]["gas_selector"].get()
                gas_selector_widget.setCurrentIndex(
                    self.gas_mapper[f"{indx_mnf + 1}"][gas]
                )
                gas_selector_widget.currentIndexChanged.connect(self.select_gases)
            # set signal handling of gas channle enable widgets

            for indx_mnf in range(8):  # going over manifold gas enable checkboxes
                mnf = f"{indx_mnf + 1}"
                enable_checkBox = getattr(self, f"checkBox_ch{ch}_mnf{mnf}_enable")
                # checking if the upstream and downstream valves are open and setting checkbox state
                upstream_vlv_st = self.ghs["channels"][ch][
                    f"mnf{mnf}_vlv_upstream"
                ].get()
                dnstream_vlv_st = self.ghs["channels"][ch][
                    f"mnf{mnf}_vlv_dnstream"
                ].get()
                if upstream_vlv_st and dnstream_vlv_st:
                    enable_checkBox.setChecked(True)
                else:
                    enable_checkBox.setChecked(False)
                enable_checkBox.stateChanged.connect(self.toggle_channels)

                # setting MFC widgets to the PV setpoint values
                value = self.ghs["channels"][ch][f"mfc{indx_mnf + 1}_sp"].get()
                mfc_sp_object = getattr(
                    self, f"spinBox_ch{ch}_mnf{indx_mnf + 1}_mfc_sp"
                )
                mfc_sp_object.setValue(value)
                mfc_sp_object.editingFinished.connect(self.set_flow_rates)

        self._archiver_poller = ArchiverPoller(self.archiver, self)
        self._archiver_poller.ready.connect(self._accept_archiver_snapshot)
        self._archiver_poller.failed.connect(self._archiver_failed)
        self.timer_read_archiver = QtCore.QTimer(self)
        self.timer_read_archiver.setInterval(2000)
        self.timer_read_archiver.timeout.connect(self.read_archiver)
        self.timer_read_archiver.singleShot(0, self.read_archiver)
        self.timer_read_archiver.start()

        self.timer_update_time = QtCore.QTimer(self)
        self.timer_update_time.setInterval(2000)
        self.timer_update_time.timeout.connect(self.update_status)
        self.timer_update_time.singleShot(0, self.update_status)
        self.timer_update_time.start()

        self.timer_sample_env_status = QtCore.QTimer(self)
        self.timer_sample_env_status.setInterval(500)
        self.timer_sample_env_status.timeout.connect(self.update_sample_env_status)
        self.timer_sample_env_status.singleShot(0, self.update_sample_env_status)
        self.timer_sample_env_status.start()

        self.spinBox_steps.valueChanged.connect(self.manage_number_of_steps)
        self.tableWidget_program.cellChanged.connect(self.handle_program_changes)

        self.pushButton_visualize_program.clicked.connect(
            self.parse_and_vizualize_program
        )
        self.pushButton_export.clicked.connect(self.save_gas_program)
        self.pushButton_load.clicked.connect(self.load_gas_program)
        self.pushButton_reset.clicked.connect(self.reset_gas_program)
        self.process_program_steps = {}

        self.combo_box_options = {
            "None": ["None"],
            "GHS Ch1": ["He", "N2", "Ar", "O2", "CO2", "C2H4"],
            "GHS Ch2": ["He", "N2", "Ar", "O2", "CO2", "C2H4"],
            "Gas cart": ["H2", "CO", "CH4"],
        }

        for indx in range(5):
            combo_source = getattr(self, f"comboBox_source_of_gas{indx + 1}")
            combo_source.addItems(self.combo_box_options.keys())
            combo_gas = getattr(self, f"comboBox_gas{indx + 1}")
            combo_gas.addItems(self.combo_box_options["None"])
            combo_source.currentIndexChanged.connect(self.update_comboBox_gas)

    def actuate_condition_valves(self):
        sender_object = self.sender()
        name = sender_object.objectName()
        valve_name = name[12:18]
        valve_status = name[19:]

        if valve_status == "close":
            getattr(self.flow_condition_valves, valve_name).put(0)
        elif valve_status == "open":
            getattr(self.flow_condition_valves, valve_name).put(1)

    def set_vacuum_pump_off(self):
        self.pdu.module7.put(0)

    def set_vacuum_pump_on(self):
        self.pdu.module7.put(1)

    def update_comboBox_gas(self):
        sender_object = self.sender()
        indx = sender_object.objectName()[-1]
        source_key = sender_object.currentText()
        combo_gas = getattr(self, f"comboBox_gas{indx}")
        combo_gas.clear()
        combo_gas.addItems(self.combo_box_options[source_key])

    def reset_gas_program(self):
        self.tableWidget_program.setColumnCount(1)
        self.tableWidget_program.setRowCount(8)

        for i in range(1, 6):
            getattr(self, "comboBox_gas" + str(i)).setCurrentIndex(0)
            item = QtWidgets.QTableWidgetItem(str(0))
            item.setCheckState(2)
            self.tableWidget_program.setItem(0, i + 2, item)

        self.current_sample_env.ramp_stop()

    def save_gas_program(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save File", str(Path.home()), "Excel workbooks (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            self.create_gas_program_dict()
            self.create_dataframe().to_excel(path)
        except (OSError, ValueError) as exc:
            message_box("Error saving program", str(exc))

    def create_dataframe(self):
        return program_dataframe(self.process_program_steps)

    def load_gas_program(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open File", str(Path.home()), "Excel workbooks (*.xlsx)"
        )
        if not path:
            return
        try:
            self.create_table_using_xlsx_file(path)
        except (OSError, ValueError, KeyError) as exc:
            message_box("Error loading program", str(exc))

    def create_table_using_xlsx_file(self, path):
        _df = pd.read_excel(path, index_col=0)
        no_of_steps = int((len(_df.columns) - 3) / 2)
        with (
            QtCore.QSignalBlocker(self.tableWidget_program),
            QtCore.QSignalBlocker(self.spinBox_steps),
        ):
            self.spinBox_steps.setValue(no_of_steps)
            self.tableWidget_program.setColumnCount(no_of_steps)
            self.tableWidget_program.setRowCount(8)

            for i, source in enumerate(_df["source"].iloc[3:], start=1):
                if type(source) is str:
                    getattr(self, f"comboBox_source_of_gas{i}").setCurrentText(source)
                else:
                    getattr(self, f"comboBox_source_of_gas{i}").setCurrentIndex(0)

            for i, gas in enumerate(_df["gas"].iloc[3:], start=1):
                if type(gas) is str:
                    getattr(self, f"comboBox_gas{i}").setCurrentText(gas)
                else:
                    getattr(self, f"comboBox_gas{i}").setCurrentIndex(0)

            for step in range(1, no_of_steps + 1):
                for i, (value, direction) in enumerate(
                    zip(_df[step], _df[f"direction_{step}"])
                ):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if type(direction) is str:
                        if direction == "reactor":
                            item.setCheckState(2)
                        else:
                            item.setCheckState(0)
                    self.tableWidget_program.setItem(i, step - 1, item)

    def init_table_widget(self):
        self.manage_number_of_steps()
        self.tableWidget_program.setVerticalHeaderLabels(
            (
                "Temperature, C°",
                "Duration, min",
                "Ramp rate, C°/min",
                "Flow rate 1, sccm",
                "Flow rate 2, sccm",
                "Flow rate 3, sccm",
                "Flow rate 4, sccm",
                "Flow rate 5, sccm",
            )
        )

    def manage_number_of_steps(self):
        no_of_steps = self.spinBox_steps.value()
        with QtCore.QSignalBlocker(self.tableWidget_program):
            self.tableWidget_program.setColumnCount(no_of_steps)
            self.tableWidget_program.setRowCount(8)
            for row in range(3, 8):
                for column in range(no_of_steps):
                    if self.tableWidget_program.item(row, column) is None:
                        item = QtWidgets.QTableWidgetItem("0")
                        item.setCheckState(QtCore.Qt.Checked)
                        self.tableWidget_program.setItem(row, column, item)

    def handle_program_changes(self, row, column):
        def ramp_driven(column, t_range):
            ramp_rate = self.tableWidget_program.item(1, column).text()
            try:
                ramp_rate = int(float(ramp_rate))
                duration = t_range / ramp_rate
                item = QtWidgets.QTableWidgetItem(str(duration))
                item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
                self.tableWidget_program.setItem(2, column, item)
                self.tableWidget_program.item(1, column).setForeground(
                    QtGui.QBrush(QtGui.QColor(0, 0, 0))
                )
                self.step_priority[column] = 1  # one is priority on ramp
            except Exception as e:
                message_box(
                    "Error 5",
                    "Non numerical value entered. Resetting to default value. Please check",
                )
                print(e)
                item = QtWidgets.QTableWidgetItem("10")
                self.tableWidget_program.setItem(1, column, item)

        def duration_driven(column, t_range):
            duration = self.tableWidget_program.item(2, column).text()
            try:
                duration = int(float(duration))
                ramp = t_range / duration
                item = QtWidgets.QTableWidgetItem(str(ramp))
                item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
                self.tableWidget_program.setItem(1, column, item)
                self.tableWidget_program.item(2, column).setForeground(
                    QtGui.QBrush(QtGui.QColor(0, 0, 0))
                )
                self.step_priority[column] = 2  # one is priority on duration
            except Exception as e:
                message_box(
                    "Error 4",
                    "Non numerical value entered. Resetting to default value. Please check",
                )
                print(e)
                item = QtWidgets.QTableWidgetItem("10")
                self.tableWidget_program.setItem(2, column, item)

        with QtCore.QSignalBlocker(self.tableWidget_program):
            sample_env = self.current_sample_env
            temperature = None
            previous_temperature = None
            if column > 0:
                if self.tableWidget_program.item(0, column - 1):
                    if self.tableWidget_program.item(0, column - 1).text() != "":
                        previous_temperature = int(
                            float(self.tableWidget_program.item(0, column - 1).text())
                        )
                if self.tableWidget_program.item(0, column):
                    temperature = int(
                        float(self.tableWidget_program.item(0, column).text())
                    )
            else:
                previous_temperature = np.round(sample_env.pv.get())
                if previous_temperature > 1300:
                    print("Thermocouple is disconnected")
                    previous_temperature = 25
                if self.tableWidget_program.item(0, column):
                    if self.tableWidget_program.item(0, column).text() != "":
                        temperature = int(
                            float(self.tableWidget_program.item(0, column).text())
                        )
            if temperature and previous_temperature:
                t_range = temperature - previous_temperature
                if row == 0:
                    if self.tableWidget_program.item(1, column):
                        ramp_driven(column, t_range)
                    elif self.tableWidget_program.item(2, column):
                        duration_driven(column, t_range)
                if row == 1:
                    if self.tableWidget_program.item(1, column):  # ramp
                        ramp_driven(column, t_range)
                elif row == 2:
                    if self.tableWidget_program.item(2, column):  # duration
                        duration_driven(column, t_range)

            if row > 2:
                flow_rate = self.tableWidget_program.item(row, column).text()
                flag = True
                try:
                    float(flow_rate)
                except ValueError:
                    message_box(
                        "Error",
                        "Non numerical value entered. Resetting to default value. Please re-check",
                    )
                    flag = False
                if not flag:
                    item = QtWidgets.QTableWidgetItem("0")
                    item.setCheckState(2)
                    self.tableWidget_program.setItem(row, column, item)
                if flag:
                    for j in range(self.spinBox_steps.value()):
                        _is_empty = False
                        if j != column:
                            if self.tableWidget_program.item(row, j):
                                if self.tableWidget_program.item(row, j).text() == "":
                                    _is_empty = True
                            else:
                                _is_empty = True
                            if _is_empty:
                                item = QtWidgets.QTableWidgetItem("0")
                                item.setCheckState(2)
                                self.tableWidget_program.setItem(row, j, item)

    def create_gas_program_dict(self):
        self.process_program_steps = {}
        no_of_columns = self.tableWidget_program.columnCount()

        _tmp = {
            "temp": None,
            "duration": None,
            "rate": None,
            "flow_1": None,
            "flow_2": None,
            "flow_3": None,
            "flow_4": None,
            "flow_5": None,
        }
        for col in range(no_of_columns):
            self.process_program_steps[col] = {}

            for i, key in enumerate(["temp", "duration", "rate"]):
                _tmp[key] = self.tableWidget_program.item(i, col)
                if _tmp[key]:
                    try:
                        _value = float(_tmp[key].text())
                        self.process_program_steps[col][key] = _value
                    except ValueError:
                        message_box("Error", "Enter numerical value")
                else:
                    self.process_program_steps[col][key] = None

            for j, gas_key in enumerate(
                ["flow_1", "flow_2", "flow_3", "flow_4", "flow_5"], start=3
            ):
                _tmp[gas_key] = self.tableWidget_program.item(j, col)

                if _tmp[gas_key]:
                    self.process_program_steps[col][gas_key] = {}
                    self.process_program_steps[col][gas_key]["source"] = getattr(
                        self, f"comboBox_source_of_gas{j - 2}"
                    ).currentText()
                    self.process_program_steps[col][gas_key]["name"] = getattr(
                        self, f"comboBox_gas{j - 2}"
                    ).currentText()
                    self.process_program_steps[col][gas_key]["to_reactor"] = (
                        _tmp[gas_key].checkState() == 2
                    )
                    try:
                        _value = float(_tmp[gas_key].text())
                        self.process_program_steps[col][gas_key]["flow"] = float(
                            _tmp[gas_key].text()
                        )
                    except ValueError:
                        message_box("Error", "Enter numerical values")
                        self.process_program_steps[col][gas_key]["flow"] = -1
                else:
                    self.process_program_steps[col][gas_key] = None

    def parse_and_vizualize_program(self):
        self.create_gas_program_dict()
        self.visualize_temperature_program()

    def read_program_data(self):
        times = []
        sps = []
        for i, key in enumerate(self.process_program_steps):
            if (
                self.process_program_steps[i]["temp"]
                and self.process_program_steps[i]["duration"]
            ):
                times.append(self.process_program_steps[i]["duration"])
                sps.append(self.process_program_steps[i]["temp"])

        times = np.cumsum(times)
        times = np.hstack((0, np.array(times))) * 60
        starting_temp = self.current_sample_env.current_pv_reading()
        if int(starting_temp) > 1300:
            starting_temp = 25
        sps = np.hstack((starting_temp, np.array(sps)))
        print("The parsed program:")
        for _time, _sp in zip(times, sps):
            print("time", _time, "\ttemperature", _sp)
        self.process_program = {"times": times.tolist(), "setpoints": sps.tolist()}

        df = self.create_dataframe()

        flows = {}
        for indx in range(3, 8):
            flows[f"flowgas{indx - 2}"] = df.loc[indx]["gas"]
            flows[f"flowsource{indx - 2}"] = df.loc[indx]["source"]
            flows[f"flowprog{indx - 2}"] = df.loc[indx].iloc[3::2].tolist()
            flows[f"flowprog{indx - 2}"].insert(0, 0)
            flows[f"flowdirection{indx - 2}"] = df.loc[indx].iloc[4::2].tolist()
            flows[f"flowdirection{indx - 2}"].insert(0, 0)
        self.process_program = {**self.process_program, **flows}

    def visualize_temperature_program(self):
        self.read_program_data()
        self.plot_program_flag = True
        self.program_plot_moving_flag = True
        self.update_plot_program_data()
        self.update_status()

    def addCanvas(self):
        self.figure_rga = Figure()
        self.figure_rga.set_facecolor(color="#efebe7")
        self.figure_rga.ax = self.figure_rga.add_subplot(111)
        self.canvas_rga = FigureCanvas(self.figure_rga)
        self.toolbar_rga = NavigationToolbar(self.canvas_rga, self)
        self.layout_rga.addWidget(self.canvas_rga)
        self.layout_rga.addWidget(self.toolbar_rga)
        self.canvas_rga.draw()

        self.figure_mfc = Figure()
        self.figure_mfc.set_facecolor(color="#efebe7")
        self.figure_mfc.ax = self.figure_mfc.add_subplot(111)
        self.canvas_mfc = FigureCanvas(self.figure_mfc)
        self.toolbar_mfc = NavigationToolbar(self.canvas_mfc, self)
        self.layout_mfc.addWidget(self.canvas_mfc)
        self.layout_mfc.addWidget(self.toolbar_mfc)
        self.canvas_mfc.draw()

        self.figure_temp = Figure()
        self.figure_temp.set_facecolor(color="#efebe7")
        self.figure_temp.ax = self.figure_temp.add_subplot(111)
        self.canvas_temp = FigureCanvas(self.figure_temp)
        self.toolbar_temp = NavigationToolbar(self.canvas_temp, self)
        self.layout_temp.addWidget(self.canvas_temp)
        self.layout_temp.addWidget(self.toolbar_temp)
        self.canvas_temp.draw()

    def reset_cart_plc(self):
        self.mobile_gh_system.reset()

    def sample_env_selected(self):
        _current_key = self.comboBox_sample_envs.currentText()
        self.current_sample_env = self.sample_envs_dict[_current_key]
        self.init_table_widget()

    def update_ghs_status(self):
        # update card MFC setpoints and readbacks
        for indx in range(4):
            mfc_rb_widget = getattr(self, f"spinBox_cart_mfc{indx + 1}_rb")
            rb = self.gas_cart[indx + 1]["mfc"].rb.get()
            mfc_rb_widget.setText(f"{rb:.1f} sccm")
            mfc_sp_widget = getattr(self, f"spinBox_cart_mfc{indx + 1}_sp")
            st = mfc_sp_widget.blockSignals(True)
            sp = self.gas_cart[indx + 1]["mfc"].sp.get()
            if not mfc_sp_widget.hasFocus():
                mfc_sp_widget.setValue(sp)
            mfc_sp_widget.blockSignals(st)

            # Check if the setpoints and readbacks are close
            status_label = getattr(self, f"label_cart_mfc{indx + 1}_status")
            if sp > 0:
                error = np.abs((rb - sp) / sp)
                if error > 0.1:
                    status_label.setStyleSheet("background-color: rgb(255,0,0)")
                elif error > 0.02:
                    status_label.setStyleSheet("background-color: rgb(255,240,24)")
                else:
                    status_label.setStyleSheet("background-color: rgb(0,255,0)")
            else:
                status_label.setStyleSheet("background-color: rgb(171,171,171)")
            if self.gas_cart[indx + 1]["vlv"] is not None:
                vlv_status = self.gas_cart[indx + 1]["vlv"].status.get()
                if vlv_status:
                    getattr(self, f"label_cart_vlv{indx + 1}_status").setStyleSheet(
                        "background-color: rgb(0,255,0)"
                    )
                else:
                    getattr(self, f"label_cart_vlv{indx + 1}_status").setStyleSheet(
                        "background-color: rgb(255,0,0)"
                    )

        # Check rector/exhaust status
        for indx_ch in range(2):
            for outlet in ["reactor", "exhaust"]:
                status_label = getattr(self, f"label_ch{indx_ch + 1}_{outlet}_status")

                if self.ghs["channels"][f"{indx_ch + 1}"][outlet].get():
                    status_label.setStyleSheet("background-color: rgb(0,255,0)")
                else:
                    status_label.setStyleSheet("background-color: rgb(255,0,0)")

            for indx_mnf in range(8):
                mfc_sp_widget = getattr(
                    self, f"spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp"
                )
                mfc_rb_label = getattr(
                    self, f"label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_rb"
                )
                rb = self.ghs["channels"][f"{indx_ch + 1}"][
                    f"mfc{indx_mnf + 1}_rb"
                ].get()
                value = f"{rb:.2f} sccm"

                mfc_rb_label.setText(value)

                mfc_sp_widget = getattr(
                    self, f"spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp"
                )
                st = mfc_sp_widget.blockSignals(True)
                value = self.ghs["channels"][f"{indx_ch + 1}"][
                    f"mfc{indx_mnf + 1}_sp"
                ].get()
                if not mfc_sp_widget.hasFocus():
                    mfc_sp_widget.setValue(value)
                mfc_sp_widget.blockSignals(st)

                sp = value
                status_label = getattr(
                    self, f"label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_status"
                )

                # Check if the setpoints and readbacks are close
                if sp > 0:
                    error = np.abs((rb - sp) / sp)
                    if error > 0.1:
                        mfc_rb_label.setStyleSheet("background-color: rgb(255,0,0)")
                    elif error > 0.02:
                        mfc_rb_label.setStyleSheet("background-color: rgb(255,240,24)")
                    else:
                        mfc_rb_label.setStyleSheet("background-color: rgb(0,255,0)")
                else:
                    mfc_rb_label.setStyleSheet("background-color: rgb(171,171,171)")

        for indx_ch in range(2):
            for indx_mnf in range(8):
                upstream_valve_label = getattr(
                    self, f"label_ch{indx_ch + 1}_valve{indx_mnf + 1}_status"
                )
                dnstream_valve_label = getattr(
                    self, f"label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_status"
                )

                upstream_valve_status = self.ghs["channels"][f"{indx_ch + 1}"][
                    f"mnf{indx_mnf + 1}_vlv_upstream"
                ].get()
                dnstream_valve_status = self.ghs["channels"][f"{indx_ch + 1}"][
                    f"mnf{indx_mnf + 1}_vlv_dnstream"
                ].get()
                if upstream_valve_status == 0:
                    upstream_valve_label.setStyleSheet("background-color: rgb(255,0,0)")
                else:
                    upstream_valve_label.setStyleSheet("background-color: rgb(0,255,0)")

                if dnstream_valve_status == 0:
                    dnstream_valve_label.setStyleSheet("background-color: rgb(255,0,0)")
                else:
                    dnstream_valve_label.setStyleSheet("background-color: rgb(0,255,0)")

        if self.checkBox_total_flow_open.isChecked():
            self.total_flow_meter.sp.set(100)
        else:
            self.total_flow_meter.sp.set(0)
        self.label_total_flow.setText(f"{str(self.total_flow_meter.get().rb)} sccm")

        for element, valve in self.switch_manifold.items():
            valve_reactor_label = getattr(self, f"label_switch_{element}_reactor")
            valve_exhaust_label = getattr(self, f"label_switch_{element}_exhaust")
            if valve.state.get() == 1:
                valve_reactor_label.setStyleSheet("background-color: rgb(0,255,0)")
                valve_exhaust_label.setStyleSheet("background-color: rgb(255,0,0)")
            else:
                valve_reactor_label.setStyleSheet("background-color: rgb(255,0,0)")
                valve_exhaust_label.setStyleSheet("background-color: rgb(0,255,0)")

    def update_sample_env_status(self):
        sample_env = self.current_sample_env
        self.label_pv_rb.setText(
            f"{sample_env.pv_name} RB: {np.round(sample_env.pv.get(), 2)} {sample_env.pv_units}"
        )
        self.label_pv_sp.setText(
            f"{sample_env.pv_name} SP: {np.round(sample_env.pv_sp.get(), 2)} {sample_env.pv_units}"
        )
        self.label_pv_sp_rate.setText(
            f"{sample_env.pv_name} SP rate: {np.round(sample_env.ramper.pv_sp_rate.get(), 2)} {sample_env.pv_units}/min"
        )
        self.label_output_rb.setText(
            f"Output {sample_env.pv_output_name} RB: {np.round(sample_env.pv_output.get(), 2)} {sample_env.pv_output_units}"
        )

        if sample_env.enabled.get() == 1:
            self.label_output_pid_status.setStyleSheet("background-color: rgb(255,0,0)")
            self.label_output_pid_status.setText("ON")
        else:
            self.label_output_pid_status.setStyleSheet(
                "background-color: rgb(171,171,171)"
            )
            self.label_output_pid_status.setText("OFF")

        running = sample_env.ramper.go.get()
        paused = sample_env.ramper.pv_pause.get()
        if running == 1 and paused == 0:
            self.label_program_status.setStyleSheet("background-color: rgb(255,0,0)")
            self.label_program_status.setText("ON")
        elif running == 1 and paused == 1:
            self.label_program_status.setStyleSheet("background-color: rgb(255,240,24)")
            self.label_program_status.setText("PAUSED")
        elif running == 0:
            self.label_program_status.setStyleSheet(
                "background-color: rgb(171,171,171)"
            )
            self.label_program_status.setText("OFF")

    def read_archiver(self):
        self._archiver_poller.request(self.doubleSpinBox_timewindow.value())

    def _accept_archiver_snapshot(self, snapshot):
        self._df_ = snapshot.tables
        self.now = snapshot.end
        self.some_time_ago = snapshot.start
        self.timewindow = snapshot.timewindow

    def _archiver_failed(self, message):
        logger.warning("Archiver read failed: %s", message)

    def closeEvent(self, event):
        self.timer_read_archiver.stop()
        self.timer_update_time.stop()
        self.timer_sample_env_status.stop()
        self._archiver_poller.close()
        super().closeEvent(event)

    def update_plotting_status(self):

        if self._df_ is None:
            return

        data_format = mdates.DateFormatter("%H:%M:%S", tz="US/Eastern")

        self._xlim_num = (
            pd.to_datetime([self.some_time_ago, self.now], unit="s", utc=True)
            .tz_convert("US/Eastern")
            .tolist()
        )

        # handling the xlim extension due to the program vizualization
        if self.plot_program_flag:
            if self._plot_temp_program is not None:
                self._xlim_num[1] = np.max(
                    [self._plot_temp_program["time"].iloc[-1], self._xlim_num[1]]
                )
        _xlim = self._xlim_num

        masses = []
        for rga_mass in self.rga_masses:
            masses.append(str(rga_mass.get()))

        update_figure([self.figure_rga.ax], self.toolbar_rga, self.canvas_rga)
        for rga_ch, mass in zip(self.rga_channels, masses):
            dataset = self._df_[rga_ch.name]
            indx = rga_ch.name[-1]
            if getattr(self, f"checkBox_rga{indx}").isChecked():
                self.figure_rga.ax.plot(
                    dataset["time"], dataset["data"], label=f"{mass} amu"
                )
        self.figure_rga.ax.grid(alpha=0.4)
        self.figure_rga.ax.xaxis.set_major_formatter(data_format)
        self.figure_rga.ax.set_xlim(_xlim)
        self.figure_rga.ax.autoscale_view(tight=True)
        if not np.isfinite(self.figure_rga.ax.dataLim.minposy):
            self.figure_rga.ax.set_ylim(1e-12, 1)
        self.figure_rga.ax.set_yscale("log")
        self.figure_rga.tight_layout()
        if self.figure_rga.ax.lines:
            self.figure_rga.ax.legend(loc=6)
        self.canvas_rga.draw_idle()

        update_figure([self.figure_mfc.ax], self.toolbar_mfc, self.canvas_mfc)

        for channels_key in ["1", "2", "3"]:
            if channels_key == "3":
                __gas_cart = ["CH4", "CO", "H2"]
                for j in range(1, 4):
                    dataset_mfc_cart = self._df_[
                        "mfc_cart_" + __gas_cart[j - 1] + "_rb"
                    ]
                    indx_gc = j
                    if getattr(self, f"checkBox_ch3_mfc{indx_gc}").isChecked():
                        self.figure_mfc.ax.plot(
                            dataset_mfc_cart["time"],
                            dataset_mfc_cart["data"],
                            label=f"Gas cart {__gas_cart[j - 1]}",
                        )

            else:
                for i in range(1, 9):
                    dataset_mfc = self._df_[
                        "ghs_ch" + channels_key + "_mfc" + str(i) + "_rb"
                    ]
                    indx_mfc = i
                    if getattr(
                        self, f"checkBox_ch{channels_key}_mfc{indx_mfc}"
                    ).isChecked():
                        self.figure_mfc.ax.plot(
                            dataset_mfc["time"],
                            dataset_mfc["data"],
                            label=f"ch{channels_key} mfc{indx_mfc}",
                        )

        self.figure_mfc.ax.grid(alpha=0.4)
        self.figure_mfc.ax.xaxis.set_major_formatter(data_format)
        self.figure_mfc.ax.set_xlim(_xlim)
        self.figure_mfc.ax.autoscale_view(tight=True)
        self.figure_mfc.ax.set_yscale("linear")
        self.figure_mfc.tight_layout()
        if self.figure_mfc.ax.lines:
            self.figure_mfc.ax.legend(loc=6)

        update_figure([self.figure_temp.ax], self.toolbar_temp, self.canvas_temp)

        dataset_rb = self._df_["temp2"]
        dataset_sp = self._df_["temp2_sp"]
        latest_time = dataset_rb["time"].iloc[-1] if not dataset_rb.empty else None
        dataset_sp = self._pad_dataset_sp(dataset_sp, latest_time)
        self.figure_temp.ax.plot(
            dataset_sp["time"], dataset_sp["data"], label="T setpoint"
        )
        self.figure_temp.ax.plot(
            dataset_rb["time"], dataset_rb["data"], label="T readback"
        )
        self.plot_pid_program()

        self.figure_temp.ax.grid(alpha=0.4)
        self.figure_temp.ax.xaxis.set_major_formatter(data_format)
        self.figure_temp.ax.set_xlim(_xlim)
        self.figure_temp.ax.set_ylim(
            self.spinBox_temp_range_min.value(), self.spinBox_temp_range_max.value()
        )
        self.figure_temp.ax.autoscale_view(tight=True)
        self.figure_temp.tight_layout()
        self.figure_temp.ax.legend(loc=6)
        self.canvas_temp.draw_idle()
        self.canvas_mfc.draw_idle()
        self._df_ = None

    def _pad_dataset_sp(self, df, latest_time, delta_thresh=15):
        return pad_setpoints(df, latest_time, delta_thresh)

    def update_status(self):
        if self.checkBox_update.isChecked():
            self.update_ghs_status()
            self.update_plotting_status()

    def visualize_program(self):
        self.read_program_data()
        self.plot_program_flag = True
        self.program_plot_moving_flag = True
        self.update_plot_program_data()
        self.update_status()

    def update_plot_program_data(self):
        if self.process_program is not None:
            times = ttime.time() + np.array(self.process_program["times"])
            self._plot_temp_program = pd.DataFrame(
                {
                    "setpoints": self.process_program["setpoints"],
                    "time_s": times,
                }
            )
            self._plot_temp_program["time"] = pd.to_datetime(
                times, unit="s", utc=True
            ).tz_convert("US/Eastern")

    def plot_pid_program(self):
        if self.plot_program_flag:
            if self.program_plot_moving_flag:
                self.update_plot_program_data()
            if self._plot_temp_program is not None:
                self.figure_temp.ax.plot(
                    self._plot_temp_program["time"],
                    self._plot_temp_program["setpoints"],
                    "k:",
                    label="Program Viz",
                )

                for i in range(1, 6):
                    if self.process_program["flowgas" + str(i)] != "None":
                        self.figure_mfc.ax.step(
                            self._plot_temp_program["time"],
                            self.process_program["flowprog" + str(i)],
                            label=f"{self.process_program['flowgas' + str(i)]} program",
                        )
                self.figure_mfc.ax.legend(loc=6)

    def clear_program(self):
        self.tableWidget_program.clear()
        self.init_table_widget()
        self.plot_program_flag = False
        self.program_plot_moving_flag = False
        self._plot_temp_program = None
        self.process_program = None
        self.update_status()
        self.current_sample_env.ramp_stop()

    def start_program(self):
        self.parse_and_vizualize_program()
        self.program_plot_moving_flag = False
        self.current_sample_env.ramp_start(self.process_program)

    def pause_program(self, value):
        if value == 1:
            self.current_sample_env.ramp_pause()
            self.push_start_program.setEnabled(False)
        else:
            self.current_sample_env.ramp_continue()
            self.push_start_program.setEnabled(True)

    def stop_program(self):
        self.current_sample_env.ramp_stop()

    def change_rga_mass(self):
        sender_object = self.sender()
        indx = sender_object.objectName()[-1]
        self.RE(bps.mv(self.rga_masses[int(indx) - 1], sender_object.value()))

    def set_mfc_cart_flow(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        value = sender_object.value()
        indx_mfc = int(re.findall(r"\d+", sender_name)[0])
        self.gas_cart[indx_mfc]["mfc"].sp.set(value)

    def toggle_exhaust_reactor(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        ch_num = sender_name[14]
        if sender_name.endswith("exhaust") and sender_object.isChecked():
            self.ghs["channels"][ch_num]["exhaust"].set(1)
            self.ghs["channels"][ch_num]["reactor"].set(0)
        if sender_name.endswith("reactor") and sender_object.isChecked():
            self.ghs["channels"][ch_num]["reactor"].set(1)
            self.ghs["channels"][ch_num]["exhaust"].set(0)

    def actuate_switching_valve(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        for element, valve in self.switch_manifold.items():
            if element in sender_name:
                if "exhaust" in sender_name:
                    valve.to_exhaust()
                elif "reactor" in sender_name:
                    valve.to_reactor()
                break

    def toggle_bypass_bubbler(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        ch_num = sender_name[14]
        bypass_num = sender_name[-1]
        if (
            sender_name.endswith("bypass1") or sender_name.endswith("bypass2")
        ) and sender_object.isChecked():
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bypass{bypass_num}"], 1))
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bubbler{bypass_num}_1"], 0))
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bubbler{bypass_num}_2"], 0))
        elif (
            sender_name.endswith("bubbler1") or sender_name.endswith("bubbler2")
        ) and sender_object.isChecked():
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bypass{bypass_num}"], 0))
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bubbler{bypass_num}_1"], 1))
            self.RE(bps.mv(self.ghs["channels"][ch_num][f"bubbler{bypass_num}_2"], 1))

    def toggle_cart_valve(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        ch_num = int(sender_name[-1])
        if sender_object.isChecked():
            self.RE(bps.mv(self.gas_cart[ch_num]["vlv"].open, 1))
        else:
            self.RE(bps.mv(self.gas_cart[ch_num]["vlv"].close, 1))

    def select_gases(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        gas = sender_object.currentText()
        indx_ch, indx_mnf = re.findall(r"\d+", sender_name)
        gas_command = self.ghs["manifolds"][indx_mnf]["gases"][gas]
        self.ghs["manifolds"][indx_mnf]["gas_selector"].set(gas_command)

        # change the gas selection for the other widget - they both come from the same source
        sub_dict = {"1": "2", "2": "1"}
        other_selector = getattr(
            self, f"comboBox_ch{sub_dict[indx_ch]}_mnf{indx_mnf}_gas"
        )
        st = other_selector.blockSignals(True)
        other_selector.setCurrentIndex(sender_object.currentIndex())
        other_selector.blockSignals(st)

    def toggle_channels(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        indx_ch, indx_mnf = re.findall(r"\d+", sender_name)
        if indx_ch == "1":
            indx_other_ch = "2"
        elif indx_ch == "2":
            indx_other_ch = "1"

        if sender_object.isChecked():
            self.ghs["channels"][indx_ch][f"mnf{indx_mnf}_vlv_upstream"].set(1)
            self.ghs["channels"][indx_ch][f"mnf{indx_mnf}_vlv_dnstream"].set(1)
        else:
            other_ch_status = getattr(
                self, f"checkBox_ch{indx_other_ch}_mnf{indx_mnf}_enable"
            ).isChecked()
            if not other_ch_status:
                self.ghs["channels"][indx_ch][f"mnf{indx_mnf}_vlv_upstream"].set(0)
            self.ghs["channels"][indx_ch][f"mnf{indx_mnf}_vlv_dnstream"].set(0)

    def set_flow_rates(self):
        sender_object = self.sender()
        sender_name = sender_object.objectName()
        indx_ch, indx_mnf = re.findall(r"\d+", sender_name)
        value = sender_object.value()
        self.ghs["channels"][indx_ch][f"mfc{indx_mnf}_sp"].set(value)

    def switch_gases(self):
        print(f"Switch activated at {ttime.ctime()}")
        if (
            self.radioButton_ch2_reactor.isChecked()
            and self.radioButton_ch1_exhaust.isChecked()
        ):
            self.radioButton_ch2_exhaust.setChecked(True)
            self.radioButton_ch1_reactor.setChecked(True)
        elif (
            self.radioButton_ch1_reactor.isChecked()
            and self.radioButton_ch2_exhaust.isChecked()
        ):
            self.radioButton_ch1_exhaust.setChecked(True)
            self.radioButton_ch2_reactor.setChecked(True)
        else:
            message_box("Error", "Check valve status")

    def reset_rga(self):
        for indx, rga_mass in enumerate(self.rga_masses):
            print(getattr(self, f"spinBox_rga_mass{indx + 1}").value())


class TempRampManager(object):
    def __init__(self, temperature=None, rate=None, duration=None):
        self.temperature = temperature
        self.rate = rate
        self.duration = duration
        self.set_rate_on_duration()
        self.set_duration_on_rate()

    def set_rate_on_duration(self):
        if self.duration:
            self.rate = (self.temperature - 25) / self.duration

    def set_duration_on_rate(self):
        if self.rate:
            self.duration = self.temperature / self.rate


if __name__ == "__main__":
    from iss_xsample.__main__ import main

    raise SystemExit(main())
