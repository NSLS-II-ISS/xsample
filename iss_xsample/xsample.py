import os
import re
import sys

import matplotlib
# matplotlib.use('WXAgg')
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pkg_resources
from PyQt5 import QtGui, QtWidgets, QtCore, uic
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from PyQt5.Qt import QSplashScreen, QObject
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, \
    NavigationToolbar2QT as NavigationToolbar
import bluesky.plan_stubs as bps

# checkBox_ch1_mnf1_enable
import threading
from matplotlib.figure import Figure
from isstools.elements.figure_update import update_figure
from datetime import timedelta, datetime
import time as ttime
from isstools.dialogs.BasicDialogs import message_box
from iss_xsample.gas_type import GasType

ui_path = pkg_resources.resource_filename('iss_xsample', 'ui/xsample_new.ui')

from pandas.plotting import register_matplotlib_converters
register_matplotlib_converters()

# gui_form = uic.loadUiType(ui_path)[0]  # Load the UI

class XsampleGui(*uic.loadUiType(ui_path)):

    def __init__(self,
                 gas_cart = [],
                 mobile_gh_system=None,
                 total_flow_meter = None,
                 rga_channels = [],
                 rga_masses = [],
                 heater_enable1 = [],
                 ghs = [],
                 switch_manifold = [],
                 RE = [],
                 archiver = [],
                 sample_envs_dict=[],
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.addCanvas()
        self.gas_cart = gas_cart
        self.total_flow_meter = total_flow_meter
        self.rga_channels = rga_channels
        self.rga_masses = rga_masses
        self.ghs = ghs
        self.mobile_gh_system = mobile_gh_system
        self.switch_manifold = switch_manifold

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

        self.process_program = None
        self.plot_program_flag = False
        self.program_plot_moving_flag = True
        self._plot_temp_program = None

        sample_envs_list = [k for k in self.sample_envs_dict.keys()]
        self.comboBox_sample_envs.addItems(sample_envs_list)
        self.comboBox_sample_envs.currentIndexChanged.connect(self.sample_env_selected)
        self.sample_env_selected()

        '''Switching manifold'''

        for element, valve in self.switch_manifold.items():
            button = getattr(self, f'radioButton_switch_{element}_{valve.direction}')
            button.setChecked(True)

        switching_buttons = [self.radioButton_switch_ghs_reactor,
                             self.radioButton_switch_cart_reactor,
                             self.radioButton_switch_inert_reactor,
                             self.radioButton_switch_ghs_exhaust,
                             self.radioButton_switch_cart_exhaust,
                             self.radioButton_switch_inert_exhaust]

        for button in switching_buttons:
            button.clicked.connect(self.actuate_switching_valve)


        self.gas_mapper = {'1': {0: 0, 4: 1, 2: 4, 3: 2, 1: 3},
                           '2': {0: 0, 2: 1, 3: 2},
                           '3': {0: 0, 1: 1, 2: 2},
                           '4': {0: 0, 1: 2, 2: 1},
                           '5': {0: 0, 1: 1, 2: 2},
                           }

        for indx in range(8):
            getattr(self, f'checkBox_rga{indx+1}').toggled.connect(self.update_status)

        for indx, rga_mass in enumerate(self.rga_masses):
            getattr(self, f'spinBox_rga_mass{indx + 1}').setValue(rga_mass.get())
            getattr(self, f'spinBox_rga_mass{indx + 1}').valueChanged.connect(self.change_rga_mass)

        #initializing mobile cart MFC readings

        for indx_mfc in range(4):
            mfc_widget = getattr(self, f'spinBox_cart_mfc{indx_mfc+1}_sp')
            mfc_widget.setValue(self.gas_cart[indx_mfc+1]['mfc'].sp.get())
            mfc_widget.editingFinished.connect(self.set_mfc_cart_flow)


        for indx_ch in range(2):
            ch = f'{indx_ch + 1}'

            # setting outlets
            for outlet in ['reactor', 'exhaust']:
                rb_outlet = getattr(self, f'radioButton_ch{indx_ch + 1}_{outlet}')
                if self.ghs['channels'][f'{indx_ch + 1}'][outlet].get():
                    rb_outlet.setChecked(True)
                else:
                    rb_outlet.setChecked(False)


            getattr(self,f'radioButton_ch{indx_ch+1}_reactor').toggled.connect(self.toggle_exhaust_reactor)
            getattr(self, f'radioButton_ch{indx_ch+1}_exhaust').toggled.connect(self.toggle_exhaust_reactor)

            getattr(self, f'radioButton_ch{indx_ch + 1}_bypass1').toggled.connect(self.toggle_bypass_bubbler)
            getattr(self, f'radioButton_ch{indx_ch + 1}_bypass2').toggled.connect(self.toggle_bypass_bubbler)

            getattr(self, f'radioButton_ch{indx_ch + 1}_bubbler1').toggled.connect(self.toggle_bypass_bubbler)
            getattr(self, f'radioButton_ch{indx_ch + 1}_bubbler2').toggled.connect(self.toggle_bypass_bubbler)

            self.checkBox_cart_vlv1.toggled.connect(self.toggle_cart_valve)
            self.checkBox_cart_vlv2.toggled.connect(self.toggle_cart_valve)
            self.checkBox_cart_vlv3.toggled.connect(self.toggle_cart_valve)

            # set signal handling of gas selector widgets
            for indx_mnf in range(5):
                gas_selector_widget = getattr(self,f'comboBox_ch{indx_ch+1}_mnf{indx_mnf+1}_gas')
                gas = self.ghs['manifolds'][f'{indx_mnf+1}']['gas_selector'].get()
                gas_selector_widget.setCurrentIndex(self.gas_mapper[f'{indx_mnf+1}'][gas])
                gas_selector_widget.currentIndexChanged.connect(self.select_gases)
            # set signal handling of gas channle enable widgets
            # rb_outlet.setChecked(True)


            for indx_mnf in range(8): # going over manifold gas enable checkboxes
                mnf = f'{indx_mnf + 1}'
                enable_checkBox = getattr(self, f'checkBox_ch{ch}_mnf{mnf}_enable')
                #print(f' here is the checkbox {enable_checkBox.objectName()}')
                #checking if the upstream and downstream valves are open and setting checkbox state
                upstream_vlv_st = self.ghs['channels'][ch][f'mnf{mnf}_vlv_upstream'].get()
                dnstream_vlv_st = self.ghs['channels'][ch][f'mnf{mnf}_vlv_dnstream'].get()
                if upstream_vlv_st and dnstream_vlv_st:
                    enable_checkBox.setChecked(True)
                else:
                    enable_checkBox.setChecked(False)
                enable_checkBox.stateChanged.connect(self.toggle_channels)

                #setting MFC widgets to the PV setpoint values
                value = self.ghs['channels'][ch][f'mfc{indx_mnf + 1}_sp'].get()
                mfc_sp_object = getattr(self, f'spinBox_ch{ch}_mnf{indx_mnf + 1}_mfc_sp')
                mfc_sp_object.setValue(value)
                mfc_sp_object.editingFinished.connect(self.set_flow_rates)

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


        ############### Gas Program #####################

        self.spinBox_steps.valueChanged.connect(self.manage_number_of_steps)
        self.tableWidget_program.cellChanged.connect(self.handle_program_changes)

        self.pushButton_visualize_program.clicked.connect(self.parse_and_vizualize_program)
        self.pushButton_export.clicked.connect(self.save_gas_program)
        self.pushButton_load.clicked.connect(self.load_gas_program)
        self.pushButton_reset.clicked.connect(self.reset_gas_program)
        self.process_program_steps = {}

        self.combo_box_options = {'None': 0,
                                  'CH4': 1,
                                  'CO': 2,
                                  'H2': 3,
                                  'He': 4,
                                  'N2': 5,
                                  'Ar': 6,
                                  'O2': 7,
                                  #'CO-ch': 8,
                                  'CO2': 9}
        for indx in range(5):
            combo = getattr(self, f'comboBox_gas{indx + 1}')
            for option in self.combo_box_options.keys():
                combo.addItem(option)

        ################## Gas program ###################

    def reset_gas_program(self):
        self.tableWidget_program.setColumnCount(1)
        self.tableWidget_program.setRowCount(8)

        for i in range(1, 6):
            getattr(self, 'comboBox_gas' + str(i)).setCurrentIndex(0)
            item = QtWidgets.QTableWidgetItem(str(0))
            self.tableWidget_program.setItem(0, i+2, item)

        self.current_sample_env.ramp_stop()

    def save_gas_program(self):
        try:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save File',
                                                            '/home/xf08id/Documents/xsample_program/',
                                                            '*.xlsx')
        except Exception as e:
            print('Error: ', e)
        df = self.create_dataframe()
        try:
            df.to_excel(path + '.xlsx')
        except:
            pass

    def create_dataframe(self):
        param = ['temp', 'duration', 'rate', 'flow1', 'flow2', 'flow3', 'flow4', 'flow5']
        _ch = [0, 0, 0]
        _gas = [0, 0, 0]
        for i in range(1, 6):
            if self.process_program_steps[0]['flow_' + str(i)]:
                _ch.append(self.process_program_steps[0]['flow_' + str(i)]['channel'])
                _gas.append(self.process_program_steps[0]['flow_' + str(i)]['name'])
            else:
                _ch.append(-1)
                _gas.append(-1)

        _df = pd.DataFrame()
        _df['param'] = param
        _df['channel'] = _ch
        _df['gas'] = _gas

        for i, key in enumerate(self.process_program_steps.keys()):
            _value = []
            _value.append(self.process_program_steps[key]['temp'])
            _value.append(self.process_program_steps[key]['duration'])
            _value.append(self.process_program_steps[key]['rate'])
            for j in range(1, 6):
                if self.process_program_steps[i]['flow_' + str(j)]:
                    _value.append(self.process_program_steps[i]['flow_' + str(j)]['flow'])
                else:
                    _value.append(-1)
            _df[i + 1] = _value

        return _df

    def load_gas_program(self):
        try:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open File',
                                                            '/home/xf08id/Documents/xsample_program/',
                                                            '*.xlsx')
        except Exception as e:
            print("Error: ", e)

        try:
            self.create_table_using_xlsx_file(path)
        except:
            pass

    def create_table_using_xlsx_file(self, path):
        _df = pd.read_excel(path, index_col=0)
        no_of_steps = len(_df.columns) - 3
        self.tableWidget_program.setColumnCount(no_of_steps)
        self.tableWidget_program.setRowCount(8)

        for i, ch in enumerate(_df['channel'][3:], start=1):
            if ch == 1:
                getattr(self, 'radioButton_f' + str(i) + '_' + str(ch)).setChecked(True)
            elif ch == 2:
                getattr(self, 'radioButton_f' + str(i) + '_' + str(ch)).setChecked(True)

        for i, gas in enumerate(_df['gas'][3:], start=1):
            if type(gas) is str:
                getattr(self, 'comboBox_gas' + str(i)).setCurrentIndex(self.combo_box_options[gas])
            else:
                getattr(self, 'comboBox_gas' + str(i)).setCurrentIndex(0)

        for step in range(1, no_of_steps + 1):
            for i, value in enumerate(_df[step]):
                item = QtWidgets.QTableWidgetItem(str(value))
                self.tableWidget_program.setItem(i, step - 1, item)

    def init_table_widget(self):
        self.manage_number_of_steps()
        self.tableWidget_program.setVerticalHeaderLabels(('Temperature, C°', 'Duration, min', 'Ramp rate, C°/min',
                                                          'Flow rate 1, sccm', 'Flow rate 2, sccm',
                                                          'Flow rate 3, sccm', 'Flow rate 4, sccm',
                                                          'Flow rate 5, sccm'
                                                          ))



    def manage_number_of_steps(self):
        no_of_steps = self.spinBox_steps.value()
        self.tableWidget_program.setColumnCount(no_of_steps)
        self.tableWidget_program.setRowCount(8)

        #zero padding
        for _row in range(3,8):
            for _column in range(no_of_steps):
                flow_rate = self.tableWidget_program.item(_row, _column)
                if flow_rate:
                    break
            for _column in range(no_of_steps):
                flow_rate = self.tableWidget_program.item(_row, _column)
                if not flow_rate:
                    item = QtWidgets.QTableWidgetItem('0')
                    self.tableWidget_program.setItem(_row, _column, item)








    def handle_program_changes(self, row, column):
        def ramp_driven(column, t_range):
            ramp_rate = self.tableWidget_program.item(1, column).text()
            try:
                ramp_rate = int(ramp_rate)
                duration = t_range / ramp_rate
                item = QtWidgets.QTableWidgetItem(str(duration))
                item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
                self.tableWidget_program.setItem(2, column, item)
                self.tableWidget_program.item(1, column).setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                self.step_priority[column] = 1  # one is priority on ramp
            except:
                message_box('Error 5', 'Non numerical value entered. Resetting to default value. Please check')
                item = QtWidgets.QTableWidgetItem('10')
                self.tableWidget_program.setItem(1, column, item)

        def duration_driven(column, t_range):
            duration = self.tableWidget_program.item(2, column).text()
            try:
                duration = int(duration)
                ramp = t_range / duration
                item = QtWidgets.QTableWidgetItem(str(ramp))
                item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
                self.tableWidget_program.setItem(1, column, item)
                self.tableWidget_program.item(2, column).setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                self.step_priority[column] = 2  # one is priority on duration
            except:
                message_box('Error 4','Non numerical value entered. Resetting to default value. Please check')
                item = QtWidgets.QTableWidgetItem('10')
                self.tableWidget_program.setItem(2, column, item)
        self.tableWidget_program.cellChanged.disconnect(self.handle_program_changes)
        sample_env = self.current_sample_env
        # print(f'{row = }, {column = } is changed')
        temperature = None
        previous_temperature = None
        if column > 0:
            if self.tableWidget_program.item(0, column - 1):
                if self.tableWidget_program.item(0, column - 1).text()!= '':
                    previous_temperature = int(self.tableWidget_program.item(0, column - 1).text())
            if self.tableWidget_program.item(0, column):
                temperature = int(self.tableWidget_program.item(0, column).text())
        else:
            previous_temperature = np.round(sample_env.pv.get())
            if previous_temperature >1300:
                print('Thermocouple is disconnected')
                previous_temperature= 25
            if self.tableWidget_program.item(0, column):
                if self.tableWidget_program.item(0, column).text() != '':
                    temperature = int(self.tableWidget_program.item(0, column).text())
        if temperature and previous_temperature:
            t_range = temperature - previous_temperature
            if row == 0:
                if self.tableWidget_program.item(1, column):
                    ramp_driven(column,t_range)
                elif self.tableWidget_program.item(2, column):
                    duration_driven(column,t_range)
            if row == 1:
                if self.tableWidget_program.item(1, column): #ramp
                    ramp_driven(column, t_range)
            elif row ==2:
                if self.tableWidget_program.item(2, column): #duration
                    duration_driven(column, t_range)

        if row > 2:
            flow_rate = self.tableWidget_program.item(row, column).text()
            flag = True
            try:
               float(flow_rate)
               # if flow_rate < 0:
               #     message_box('Error', 'Negative value entered. Resetting to default value. Please re-check')
               #     flag = False
            except:
                message_box('Error', 'Non numerical value entered. Resetting to default value. Please re-check')
                flag = False
            if flag == False:
                item = QtWidgets.QTableWidgetItem('0')
                self.tableWidget_program.setItem(row, column, item)
            if flag == True:
                for j in range(self.spinBox_steps.value()):
                    _is_empty = False
                    if j != column:
                        if self.tableWidget_program.item(row, j):
                            if self.tableWidget_program.item(row, j).text() == '':
                                _is_empty = True
                        else:
                            _is_empty = True
                        if _is_empty:
                            item = QtWidgets.QTableWidgetItem('0')
                            self.tableWidget_program.setItem(row, j, item)









        #
        #
        #
        # if row > 2:
        #     item = QtWidgets.QTableWidgetItem('0')
        #     try:
        #         float(self.tableWidget_program.item(row, column).text())
        #     except:
        #         self.tableWidget_program.setItem(row, column, item)
        #
        #     if float(self.tableWidget_program.item(row, column).text())<0:
        #         self.tableWidget_program.setItem(row, column, item)

        self.tableWidget_program.cellChanged.connect(self.handle_program_changes)


    def create_gas_program_dict(self):
        self.process_program_steps = {}
        no_of_columns = self.tableWidget_program.columnCount()

        _tmp = {'temp': None,
                'duration': None,
                'rate': None,
                'flow_1': None,
                'flow_2': None,
                'flow_3': None,
                'flow_4': None,
                'flow_5': None,
                }
        for col in range(no_of_columns):

            def check_status_of_radioButton(channel=None):
                if getattr(self, 'radioButton_f' + str(channel) + '_1').isChecked():
                    return 1
                else:
                    return 2

            self.process_program_steps[col] = {}

            for i, key in enumerate(['temp', 'duration', 'rate']):
                _tmp[key] = self.tableWidget_program.item(i, col)
                if _tmp[key]:
                    try:
                        _value = float(_tmp[key].text())
                        self.process_program_steps[col][key] = _value
                    except Exception as e:
                        message_box('Error','Enter numerical value')
                else:
                    self.process_program_steps[col][key] = None

            for j, gas_key in enumerate(['flow_1', 'flow_2', 'flow_3', 'flow_4', 'flow_5'], start=3):
                _tmp[gas_key] = self.tableWidget_program.item(j, col)

                if _tmp[gas_key]:
                    self.process_program_steps[col][gas_key] = {}
                    ch = check_status_of_radioButton(j - 2)
                    self.process_program_steps[col][gas_key]['channel'] = ch
                    self.process_program_steps[col][gas_key]['name'] = getattr(self,
                                                                           'comboBox_gas' + str(
                                                                               j - 2)).currentText()

                    try:
                        _value = float(_tmp[gas_key].text())
                        self.process_program_steps[col][gas_key]['flow'] = float(_tmp[gas_key].text())
                    except Exception as e:
                        message_box('Error','Enter numerical values')
                        self.process_program_steps[col][gas_key]['flow'] = -1
                else:
                    self.process_program_steps[col][gas_key] = None

    def parse_and_vizualize_program(self):
        self.create_gas_program_dict()

        # previous_temp = 25
        # for i, key in enumerate(self.process_program_steps.keys()):
        #     if self.process_program_steps[key]['temp']:
        #
        #         print(f"previous_temp: {previous_temp}")
        #
        #         if self.process_program_steps[key]['duration'] and (self.process_program_steps[key]['duration'] > 0):
        #             self.process_program_steps[key]['rate'] = np.around(
        #                 abs((self.process_program_steps[key]['temp'] - previous_temp) / self.process_program_steps[key][
        #                     'duration']), 2)
        #
        #             print(f"rate: {self.process_program_steps[key]['rate']}")
        #
        #             item = QtWidgets.QTableWidgetItem(str(self.process_program_steps[key]['rate']))
        #             self.tableWidget_program.setItem(2, i, item)
        #             previous_temp = self.process_program_steps[key]['temp']
        #             continue
        #         elif self.process_program_steps[key]['rate'] and (self.process_program_steps[key]['rate'] > 0):
        #
        #             self.process_program_steps[key]['duration'] = np.around(
        #                 abs((self.process_program_steps[key]['temp'] - previous_temp) / self.process_program_steps[key][
        #                     'rate']), 2)
        #
        #             print(f"duration: {self.process_program_steps[key]['duration']}")
        #
        #             item = QtWidgets.QTableWidgetItem(str(self.process_program_steps[key]['duration']))
        #             self.tableWidget_program.setItem(1, i, item)
        #             previous_temp = self.process_program_steps[key]['temp']
        #
        self.visualize_temperature_program()


    def read_program_data(self):
        times = []
        sps = []
        for i, key in enumerate(self.process_program_steps):
            if self.process_program_steps[i]['temp'] and self.process_program_steps[i]['duration']:
                times.append(self.process_program_steps[i]['duration'])
                sps.append(self.process_program_steps[i]['temp'])

        times = np.cumsum(times)
        times = np.hstack((0, np.array(times))) * 60
        starting_temp = self.current_sample_env.current_pv_reading()
        if int(starting_temp) >1300:
            starting_temp = 25
        sps = np.hstack((starting_temp, np.array(sps)))
        print('The parsed program:')
        for _time, _sp in zip(times, sps):
            print('time', _time, '\ttemperature', _sp)
        self.process_program = {'times': times.tolist(), 'setpoints': sps.tolist()}

        df = self.create_dataframe()

        flows = {}
        for indx in range(3, 8):

            # if df.loc[indx]['gas'] != 'None':
            #     times = list(df.loc[indx][3:])
            #     times.insert(0, 0)
            #     flows[df.loc[indx]['gas']] = times
            flows[f'flowgas{indx-2}'] = df.loc[indx]['gas']
            flows[f'flowchannel{indx - 2}'] = df.loc[indx]['channel']
            flows[f'flowprog{indx - 2}'] = df.loc[indx][3:].tolist()
            flows[f'flowprog{indx - 2}'].insert(0,0)
        self.process_program= {**self.process_program, **flows}

    def visualize_temperature_program(self):
        self.read_program_data()
        self.plot_program_flag = True
        self.program_plot_moving_flag = True
        self.update_plot_program_data()
        self.update_status()

    ###### Gas Program ######


    def addCanvas(self):
        self.figure_rga = Figure()
        self.figure_rga.set_facecolor(color='#efebe7')
        self.figure_rga.ax = self.figure_rga.add_subplot(111)
        self.canvas_rga = FigureCanvas(self.figure_rga)
        self.toolbar_rga = NavigationToolbar(self.canvas_rga, self)
        self.layout_rga.addWidget(self.canvas_rga)
        self.layout_rga.addWidget(self.toolbar_rga)
        self.canvas_rga.draw()

        self.figure_mfc = Figure()
        self.figure_mfc.set_facecolor(color='#efebe7')
        self.figure_mfc.ax = self.figure_mfc.add_subplot(111)
        self.canvas_mfc = FigureCanvas(self.figure_mfc)
        self.toolbar_mfc = NavigationToolbar(self.canvas_mfc, self)
        self.layout_mfc.addWidget(self.canvas_mfc)
        self.layout_mfc.addWidget(self.toolbar_mfc)
        self.canvas_mfc.draw()

        self.figure_temp = Figure()
        self.figure_temp.set_facecolor(color='#efebe7')
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
        # self.manage_steps()


    def update_ghs_status(self):
        # _start = ttime.time()
        # print(f'updating ghs status: start')
        # update card MFC setpoints and readbacks
        for indx in range(4):
            mfc_rb_widget = getattr(self, f'spinBox_cart_mfc{indx + 1}_rb')
            rb = '{:.1f} sccm'.format(self.gas_cart[indx+1]['mfc'].rb.get())
            mfc_rb_widget.setText(rb)
            mfc_sp_widget = getattr(self, f'spinBox_cart_mfc{indx + 1}_sp')
            st = mfc_sp_widget.blockSignals(True)
            sp = self.gas_cart[indx+1]['mfc'].sp.get()
            if not mfc_sp_widget.hasFocus():
                mfc_sp_widget.setValue(sp)
            mfc_sp_widget.blockSignals(st)

            # Check if the setpoints and readbacks are close
            status_label = getattr(self, f'label_cart_mfc{indx + 1}_status')
            rb = float(re.findall('\d*\.?\d+', rb)[0])
            if sp > 0:
                error = np.abs((rb - sp) / sp)
                if error > 0.1:
                    status_label.setStyleSheet('background-color: rgb(255,0,0)')
                elif error > 0.02:
                    status_label.setStyleSheet('background-color: rgb(255,240,24)')
                else:
                    status_label.setStyleSheet('background-color: rgb(0,255,0)')
            else:
                status_label.setStyleSheet('background-color: rgb(171,171,171)')
            if self.gas_cart[indx+1]['vlv'] is not None:
                vlv_status = self.gas_cart[indx+1]['vlv'].status.get()
                if vlv_status:
                    getattr(self, f'label_cart_vlv{indx + 1}_status').setStyleSheet('background-color: rgb(0,255,0)')
                else:
                    getattr(self, f'label_cart_vlv{indx + 1}_status').setStyleSheet('background-color: rgb(255,0,0)')

        # Check rector/exhaust status
        for indx_ch in range(2):
            for outlet in ['reactor', 'exhaust']:
                status_label = getattr(self, f'label_ch{indx_ch + 1}_{outlet}_status')

                if self.ghs['channels'][f'{indx_ch + 1}'][outlet].get():
                    status_label.setStyleSheet('background-color: rgb(0,255,0)')
                else:
                    status_label.setStyleSheet('background-color: rgb(255,0,0)')

            for indx_mnf in range(8):
                mfc_sp_widget = getattr(self, f'spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp')
                mfc_rb_label = getattr(self, f'label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_rb')
                value = "{:.2f} sccm".format(self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_rb'].get())

                mfc_rb_label.setText(value)

                mfc_sp_widget = getattr(self, f'spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp')
                st = mfc_sp_widget.blockSignals(True)
                value = self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_sp'].get()
                if not mfc_sp_widget.hasFocus():
                    mfc_sp_widget.setValue(value)
                mfc_sp_widget.blockSignals(st)

                sp = self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_sp'].get()
                rb = self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_rb'].get()
                status_label = getattr(self, f'label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_status')

                # Check if the setpoints and readbacks are close
                if sp > 0:
                    error = np.abs((rb - sp) / sp)
                    if error > 0.1:
                        mfc_rb_label.setStyleSheet('background-color: rgb(255,0,0)')
                    elif error > 0.02:
                        mfc_rb_label.setStyleSheet('background-color: rgb(255,240,24)')
                    else:
                        mfc_rb_label.setStyleSheet('background-color: rgb(0,255,0)')
                else:
                    mfc_rb_label.setStyleSheet('background-color: rgb(171,171,171)')


        for indx_ch in range(2):
            for indx_mnf in range(8):
                upstream_valve_label =  getattr(self, f'label_ch{indx_ch + 1}_valve{indx_mnf + 1}_status')
                dnstream_valve_label = getattr(self, f'label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_status')

                upstream_valve_status = self.ghs['channels'][f'{indx_ch + 1}'][f'mnf{indx_mnf + 1}_vlv_upstream'].get()
                dnstream_valve_status = self.ghs['channels'][f'{indx_ch + 1}'][f'mnf{indx_mnf + 1}_vlv_dnstream'].get()
                if upstream_valve_status == 0:
                    upstream_valve_label.setStyleSheet('background-color: rgb(255,0,0)')
                else:
                    upstream_valve_label.setStyleSheet('background-color: rgb(0,255,0)')

                if dnstream_valve_status == 0:
                   dnstream_valve_label.setStyleSheet('background-color: rgb(255,0,0)')
                else:
                    dnstream_valve_label.setStyleSheet('background-color: rgb(0,255,0)')



        if self.checkBox_total_flow_open.isChecked():
            self.total_flow_meter.sp.set(100)
        else:
            self.total_flow_meter.sp.set(0)
        self.label_total_flow.setText(f'{str(self.total_flow_meter.get().rb)} sccm')

        for element, valve in self.switch_manifold.items():
            valve_reactor_label = getattr(self, f'label_switch_{element}_reactor')
            valve_exhaust_label = getattr(self, f'label_switch_{element}_exhaust')
            if valve.state.get() == 1:
                valve_reactor_label.setStyleSheet('background-color: rgb(0,255,0)')
                valve_exhaust_label.setStyleSheet('background-color: rgb(255,0,0)')
            else:
                valve_reactor_label.setStyleSheet('background-color: rgb(255,0,0)')
                valve_exhaust_label.setStyleSheet('background-color: rgb(0,255,0)')

        # print(f'updating ghs status: took {ttime.time() - _start}')

    def update_sample_env_status(self):
        sample_env = self.current_sample_env
        self.label_pv_rb.setText(f'{sample_env.pv_name} RB: {np.round(sample_env.pv.get(), 2)} {sample_env.pv_units}')
        self.label_pv_sp.setText(f'{sample_env.pv_name} SP: {np.round(sample_env.pv_sp.get(), 2)} {sample_env.pv_units}')
        self.label_pv_sp_rate.setText(f'{sample_env.pv_name} SP rate: {np.round(sample_env.ramper.pv_sp_rate.get(), 2)} {sample_env.pv_units}/min')
        self.label_output_rb.setText(f'Output {sample_env.pv_output_name} RB: {np.round(sample_env.pv_output.get(), 2)} {sample_env.pv_output_units}')

        if sample_env.enabled.get() == 1:
            self.label_output_pid_status.setStyleSheet('background-color: rgb(255,0,0)')
            self.label_output_pid_status.setText('ON')
        else:
            self.label_output_pid_status.setStyleSheet('background-color: rgb(171,171,171)')
            self.label_output_pid_status.setText('OFF')

        if (sample_env.ramper.go.get() == 1) and (sample_env.ramper.pv_pause.get() == 0):
            self.label_program_status.setStyleSheet('background-color: rgb(255,0,0)')
            self.label_program_status.setText('ON')
        elif (sample_env.ramper.go.get() == 1) and (sample_env.ramper.pv_pause.get() == 1):
            self.label_program_status.setStyleSheet('background-color: rgb(255,240,24)')
            self.label_program_status.setText('PAUSED')
        elif sample_env.ramper.go.get() == 0:
            self.label_program_status.setStyleSheet('background-color: rgb(171,171,171)')
            self.label_program_status.setText('OFF')

    def read_archiver(self):
        self.thread = threading.Thread(target=self._read_archiver, daemon=True)
        self.thread.start()

        # self.thread = QThread()
        # self.archiver_reader = ArchiverReader(self.archiver, self.doubleSpinBox_timewindow.value())
        # self.archiver_reader.moveToThread(self.thread)
        # self.thread.started.connect(self.archiver_reader.run)
        # self.archiver_reader.finished.connect(self._read_archiver)
        # self.archiver_reader.finished.connect(self.thread.quit)
        # self.archiver_reader.finished.connect(self.archiver_reader.deleteLater)
        # self.thread.finished.connect(self.thread.deleteLater)
        # self.thread.start()

    def _read_archiver(self):
        self.now = ttime.time()
        self.timewindow = self.doubleSpinBox_timewindow.value()
        self.some_time_ago = self.now - 3600 * self.timewindow
        df = self.archiver.tables_given_times(self.some_time_ago, self.now)
        self._df_ = df
        # self._df_ = self.archiver_reader._df_.copy()
        # self.now = self.archiver_reader.now
        # self.some_time_ago = self.archiver_reader.some_time_ago


    def update_plotting_status(self):

        if self._df_ is None:
            return

        # _start = ttime.time()
        # print(f'updating plotting status: start')
        data_format = mdates.DateFormatter('%H:%M:%S')


        self._xlim_num = [self.some_time_ago, self.now]
        # handling the xlim extension due to the program vizualization
        if self.plot_program_flag:
            if self._plot_temp_program is not None:
                self._xlim_num[1] = np.max([self._plot_temp_program['time_s'].iloc[-1], self._xlim_num[1]])
        _xlim = [ttime.ctime(self._xlim_num[0]), ttime.ctime(self._xlim_num[1])]

        masses = []
        for rga_mass in self.rga_masses:
            masses.append(str(rga_mass.get()))

        update_figure([self.figure_rga.ax], self.toolbar_rga, self.canvas_rga)
        for rga_ch, mass in zip(self.rga_channels, masses):
            dataset = self._df_[rga_ch.name]
            indx = rga_ch.name[-1]
            if getattr(self, f'checkBox_rga{indx}').isChecked():
                # put -5 in the winter, -4 in the summer
                time_delta = -4
                self.figure_rga.ax.plot(dataset['time'] + timedelta(hours=time_delta), dataset['data'], label=f'{mass} amu')
        self.figure_rga.ax.grid(alpha=0.4)
        self.figure_rga.ax.xaxis.set_major_formatter(data_format)
        self.figure_rga.ax.set_xlim(_xlim)
        self.figure_rga.ax.autoscale_view(tight=True)
        self.figure_rga.ax.set_yscale('log')
        self.figure_rga.tight_layout()
        self.figure_rga.ax.legend(loc=6)
        self.canvas_rga.draw_idle()

        update_figure([self.figure_mfc.ax], self.toolbar_mfc, self.canvas_mfc)

        for channels_key in ['1', '2', '3']:

            if channels_key == '3':
                __gas_cart = ['CH4', 'CO', 'H2']
                for j in range(1, 4):
                    dataset_mfc_cart = self._df_['mfc_cart_' + __gas_cart[j - 1] + '_rb']
                    indx_gc = j
                    if getattr(self, f'checkBox_ch3_mfc{indx_gc}').isChecked():
                        # put -5 in the winter, -4 in the summer
                        time_delta = -4
                        self.figure_mfc.ax.plot(dataset_mfc_cart['time'] + timedelta(hours=time_delta),
                                                dataset_mfc_cart['data'],
                                                label=f'Gas cart {__gas_cart[j - 1]}')

            else:
                for i in range(1, 9):
                    dataset_mfc = self._df_['ghs_ch'+channels_key+'_mfc'+str(i)+'_rb']
                    indx_mfc = i

                    if getattr(self, f'checkBox_ch{channels_key}_mfc{indx_mfc}').isChecked():
                        # put -5 in the winter, -4 in the summer
                        time_delta = -4
                        self.figure_mfc.ax.plot(dataset_mfc['time'] + timedelta(hours=time_delta), dataset_mfc['data'],
                                                label=f'ch{channels_key} mfc{indx_mfc}')

        self.figure_mfc.ax.grid(alpha=0.4)
        self.figure_mfc.ax.xaxis.set_major_formatter(data_format)
        self.figure_mfc.ax.set_xlim(_xlim)
        self.figure_mfc.ax.autoscale_view(tight=True)
        self.figure_mfc.ax.set_yscale('linear')
        self.figure_mfc.tight_layout()
        self.figure_mfc.ax.legend(loc=6)


        update_figure([self.figure_temp.ax], self.toolbar_temp, self.canvas_temp)

        dataset_rb = self._df_['temp2']
        dataset_sp = self._df_['temp2_sp']
        dataset_sp = self._pad_dataset_sp(dataset_sp, dataset_rb['time'].values[-1])

        self.figure_temp.ax.plot(dataset_sp['time'] + timedelta(hours=time_delta), dataset_sp['data'], label='T setpoint')
        self.figure_temp.ax.plot(dataset_rb['time'] + timedelta(hours=time_delta), dataset_rb['data'], label='T readback')
        self.plot_pid_program()

        self.figure_temp.ax.grid(alpha=0.4)
        self.figure_temp.ax.xaxis.set_major_formatter(data_format)
        self.figure_temp.ax.set_xlim(_xlim)
        self.figure_temp.ax.set_ylim(self.spinBox_temp_range_min.value(),
                                     self.spinBox_temp_range_max.value())
        self.figure_temp.ax.autoscale_view(tight=True)
        self.figure_temp.tight_layout()
        self.figure_temp.ax.legend(loc=6)
        self.canvas_temp.draw_idle()
        self.canvas_mfc.draw_idle()
        self._df_ = None
        # print(f'updating plotting status: took {ttime.time() - _start}')



    def _pad_dataset_sp(self, df, latest_time, delta_thresh=15):
        _time = df['time'].values
        _data = df['data'].values
        n_rows = _time.size
        idxs = np.where(np.diff(_time).astype(int) * 1e-9 > delta_thresh)[0] + 1
        time = []
        data = []
        for idx in range(n_rows):
            if idx in idxs:
                insert_time = (_time[idx] - int(0.05*1.0e9)).astype('datetime64[ns]')
                time.append(insert_time)
                data.append(_data[idx-1])
            time.append(_time[idx])
            data.append(_data[idx])

        if (time[-1] - latest_time)<0:
            time.append(latest_time)
            data.append(data[-1])
        df_out = pd.DataFrame({'time' : time, 'data' : data})
        return df_out

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
            times = (ttime.time() + np.array(self.process_program['times']))
            datetimes = [datetime.fromtimestamp(i).strftime('%Y-%m-%d %H:%M:%S') for i in times]
            self._plot_temp_program = pd.DataFrame({'time': pd.to_datetime(datetimes, format='%Y-%m-%d %H:%M:%S'),
                                                    'setpoints': self.process_program['setpoints'],
                                                    'time_s' : times})

    def plot_pid_program(self):
        if self.plot_program_flag:
            if self.program_plot_moving_flag:
                self.update_plot_program_data()
            if self._plot_temp_program is not None:
                self.figure_temp.ax.plot(self._plot_temp_program['time'],
                                         self._plot_temp_program['setpoints'], 'k:', label='Program Viz')

                for i in range(1,6):
                    if self.process_program['flowgas' + str(i)] != 'None':
                        self.figure_mfc.ax.step(self._plot_temp_program['time'], self.process_program['flowprog' + str(i)], label = f"{self.process_program['flowgas' + str(i)]} program")
                self.figure_mfc.ax.legend(loc=6)

                # for k in self.process_program.keys():
                #     if k in self.combo_box_options.keys():
                #             self.figure_mfc.ax.step(self._plot_temp_program['time'], self.process_program[k], label = f'{k} program')
                # self.figure_mfc.ax.legend(loc=6)



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
        # self.visualize_program()
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
        sender_object = QObject().sender()
        indx = sender_object.objectName()[-1]
        self.RE(bps.mv(self.rga_masses[int(indx) - 1], sender_object.value()))

    def set_mfc_cart_flow(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        value = sender_object.value()
        indx_mfc = int(re.findall(r'\d+', sender_name)[0])
        self.gas_cart[indx_mfc]['mfc'].sp.set(value)


    def toggle_exhaust_reactor(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        ch_num = sender_name[14]
        if sender_name.endswith('exhaust') and sender_object.isChecked():
            self.ghs['channels'][ch_num]['exhaust'].set(1)
            #ttime.sleep(2)
            self.ghs['channels'][ch_num]['reactor'].set(0)
        if sender_name.endswith('reactor') and sender_object.isChecked():
            self.ghs['channels'][ch_num]['reactor'].set(1)
            #ttime.sleep(2)
            self.ghs['channels'][ch_num]['exhaust'].set(0)

    def actuate_switching_valve(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        for element, valve in self.switch_manifold.items():
            if element in sender_name:
                if 'exhaust' in sender_name:
                    valve.to_exhaust()
                elif 'reactor' in sender_name:
                    valve.to_reactor()
                break

    def toggle_bypass_bubbler(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        ch_num = sender_name[14]
        bypass_num = sender_name[-1]
        if (sender_name.endswith('bypass1') or sender_name.endswith('bypass2')) and sender_object.isChecked():
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bypass{bypass_num}'], 1))
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bubbler{bypass_num}_1'], 0))
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bubbler{bypass_num}_2'], 0))
        elif (sender_name.endswith('bubbler1') or sender_name.endswith('bubbler2')) and sender_object.isChecked():
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bypass{bypass_num}'], 0))
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bubbler{bypass_num}_1'], 1))
            self.RE(bps.mv(self.ghs['channels'][ch_num][f'bubbler{bypass_num}_2'], 1))

    def toggle_cart_valve(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        ch_num = int(sender_name[-1])
        if sender_object.isChecked():
            self.RE(bps.mv(self.gas_cart[ch_num]['vlv'].open,1))
        else:
            self.RE(bps.mv(self.gas_cart[ch_num]['vlv'].close,1))

    def select_gases(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        gas = sender_object.currentText()
        #print(sender_name)
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        gas_command = self.ghs['manifolds'][indx_mnf]['gases'][gas]
        # print(f'Gas command {gas_command}')
        self.ghs['manifolds'][indx_mnf]['gas_selector'].set(gas_command)

        #change the gas selection for the other widget - they both come from the same source
        sub_dict = {'1':'2','2':'1'}
        other_selector = getattr(self, f'comboBox_ch{sub_dict[indx_ch]}_mnf{indx_mnf}_gas')
        #print(other_selector.objectName())
        st = other_selector.blockSignals(True)
        other_selector.setCurrentIndex(sender_object.currentIndex())
        other_selector.blockSignals(st)

    def toggle_channels(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        if indx_ch == '1':
            indx_other_ch = '2'
        elif indx_ch == '2':
            indx_other_ch = '1'

        if sender_object.isChecked():
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_upstream'].set(1)
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_dnstream'].set(1)
        else:
            other_ch_status = getattr(self, f'checkBox_ch{indx_other_ch}_mnf{indx_mnf}_enable').isChecked()
            if not other_ch_status:
                self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_upstream'].set(0)
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_dnstream'].set(0)

    def set_flow_rates(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        # print(sender_name)
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        value = sender_object.value()
        self.ghs['channels'][indx_ch][f'mfc{indx_mnf}_sp'].set(value)

    def switch_gases(self):
        print(f'Switch activated at {ttime.ctime()}')
        if self.radioButton_ch2_reactor.isChecked() and self.radioButton_ch1_exhaust.isChecked():
            self.radioButton_ch2_exhaust.setChecked(True)
            self.radioButton_ch1_reactor.setChecked(True)
        elif self.radioButton_ch1_reactor.isChecked() and self.radioButton_ch2_exhaust.isChecked():
            self.radioButton_ch1_exhaust.setChecked(True)
            self.radioButton_ch2_reactor.setChecked(True)
        else:
            message_box('Error', 'Check valve status')



class TempRampManager(object):
    def __init__(self, temperature=None, rate=None, duration=None):
        self.temperature = temperature
        self.rate = rate
        self.duration = duration
        self.set_rate_on_duration()
        self.set_duration_on_rate()

    def set_rate_on_duration(self):
        if self.duration:
            self.rate = (self.temperature - 25)/self.duration

    def set_duration_on_rate(self):
        if self.rate:
            self.duration = self.temperature / self.rate



class ArchiverReader(QObject):
    finished = pyqtSignal()

    def __init__(self, archiver, timewindow, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timewindow = timewindow
        self.archiver = archiver

    def run(self):
        try:
            self.now = ttime.time()
            self.some_time_ago = self.now - 3600 * self.timewindow
            df = self.archiver.tables_given_times(self.some_time_ago, self.now)
            self._df_ = df
        except:
            pass

        # print(f'reading archiver took {ttime.time() - self.now}')
        self.finished.emit()



if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main = GUI()
    main.show()

    sys.exit(app.exec_())
