import os
import re
import sys
import time as ttime
import matplotlib
matplotlib.use('WXAgg')
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pkg_resources
from PyQt5 import QtGui, QtWidgets, QtCore, uic
from PyQt5.Qt import QSplashScreen, QObject
from PyQt5.QtCore import QSettings, QThread, pyqtSignal, QTimer, QDateTime
from PyQt5.QtGui import QPixmap
from PyQt5.Qt import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, \
    NavigationToolbar2QT as NavigationToolbar
import bluesky.plan_stubs as bps


from matplotlib.figure import Figure
from isstools.elements.figure_update import update_figure
from datetime import timedelta, datetime
import time as ttime
from isstools.dialogs.BasicDialogs import message_box

ui_path = pkg_resources.resource_filename('iss_xsample', 'ui/xsample.ui')

from pandas.plotting import register_matplotlib_converters
register_matplotlib_converters()


# gui_form = uic.loadUiType(ui_path)[0]  # Load the UI

class XsampleGui(*uic.loadUiType(ui_path)):

    def __init__(self,
                 mfcs = [],
                 rga_channels = [],
                 rga_masses = [],
                 temps = [],
                 temps_sp = [],
                 heater_enable1 = [],
                 ghs = [],
                 RE = [],
                 archiver = [],
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.addCanvas()
        self.mfcs = mfcs
        self.rga_channels = rga_channels
        self.rga_masses = rga_masses
        self.temps = temps
        self.temps_sp = temps_sp
        self.heater_enable1 = heater_enable1
        self.ghs = ghs

        self.RE = RE
        self.archiver = archiver
        self.timer_update_time = QtCore.QTimer(self)
        self.timer_update_time.setInterval(2000)
        self.timer_update_time.timeout.connect(self.update_status)
        self.timer_update_time.singleShot(0, self.update_status)
        self.timer_update_time.start()

        self.program_update_time = 1 # time interval at which program set point is updated
        self.timer_program = QtCore.QTimer(self)
        self.timer_program.setInterval(self.program_update_time*1000)
        self.timer_program.timeout.connect(self.update_temp_sp)

        self.push_visualize_program.clicked.connect(self.visualize_program)
        self.push_start_program.clicked.connect(self.start_program)

        self.spinBox_CH4.valueChanged.connect(self.set_mfc_cart_flow)
        self.spinBox_CO.valueChanged.connect(self.set_mfc_cart_flow)
        self.spinBox_H2.valueChanged.connect(self.set_mfc_cart_flow)

        self.spinBox_CH4.setValue(mfcs[0].flow.get_setpoint())
        self.spinBox_CO.setValue(mfcs[1].flow.get_setpoint())
        self.spinBox_H2.setValue(mfcs[2].flow.get_setpoint())

        for indx in range(8):
            getattr(self, f'checkBox_rga{indx+1}').toggled.connect(self.update_status)


        for indx, rga_mass in enumerate(self.rga_masses):
            getattr(self, f'spinBox_rga_mass{indx + 1}').setValue(rga_mass.get())
            getattr(self, f'spinBox_rga_mass{indx + 1}').valueChanged.connect(self.change_rga_mass)



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

            # set signal handling of gas selector widgets
            for indx_mnf in range(5):
                print(self.ghs['manifolds'][indx_mnf]['gas_selector'].get)
                getattr(self,f'comboBox_ch{indx_ch+1}_mnf{indx_mnf+1}_gas').currentIndexChanged.connect(self.select_gases)
            # set signal handling of gas channle enable widgets
            rb_outlet.setChecked(True)


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
                mfc_sp_object.valueChanged.connect(self.set_flow_rates)








        self.tableWidget_program.setColumnCount(2)
        self.tableWidget_program.setRowCount(10)
        self.tableWidget_program.setHorizontalHeaderLabels(('Temperature\n setpoint', 'Time'))

        self.program_sps = None
        self.plot_program = False




    # a.setRowCount(2)
    # a.setRowCount(12)
    # a.setVerticalHeaderLabels('sd', 'sdsd')
    # a.setVerticalHeaderLabels(('sd', 'sdsd'))
    # a.setHorizontalHeaderLabels(('Temperqature setpoint', 'Time'))
    # a.setHorizontalHeaderLabels(('Temperqature\n setpoint', 'Time'))
    # a.setHorizontalHeaderLabels(('Temperature\n setpoint', 'Time'))
    # a.setHorizontalHeaderLabels(('Temperature\n setpoint', 'Time'))



    def addCanvas(self):
        self.figure_rga = Figure()
        self.figure_rga.set_facecolor(color='#FcF9F6')
        self.figure_rga.ax = self.figure_rga.add_subplot(111)
        self.canvas_rga = FigureCanvas(self.figure_rga)
        self.toolbar_rga = NavigationToolbar(self.canvas_rga, self)
        self.layout_rga.addWidget(self.canvas_rga)
        self.layout_rga.addWidget(self.toolbar_rga)
        self.canvas_rga.draw()

        self.figure_mfc = Figure()
        self.figure_mfc.set_facecolor(color='#FcF9F6')
        self.figure_mfc.ax = self.figure_mfc.add_subplot(111)
        self.canvas_mfc = FigureCanvas(self.figure_mfc)
        self.toolbar_mfc = NavigationToolbar(self.canvas_mfc, self)
        self.layout_mfc.addWidget(self.canvas_mfc)
        self.layout_mfc.addWidget(self.toolbar_mfc)
        self.canvas_mfc.draw()

        self.figure_temp = Figure()
        self.figure_temp.set_facecolor(color='#FcF9F6')
        self.figure_temp.ax = self.figure_temp.add_subplot(111)
        self.canvas_temp = FigureCanvas(self.figure_temp)
        self.toolbar_temp = NavigationToolbar(self.canvas_temp, self)
        self.layout_temp.addWidget(self.canvas_temp)
        self.layout_temp.addWidget(self.toolbar_temp)
        self.canvas_temp.draw()


    def change_rga_mass(self):
        sender_object = QObject().sender()
        indx=sender_object.objectName()[-1]
        self.RE(bps.mv(self.rga_masses[int(indx)-1],sender_object.value()))


    def update_status(self):
        if self.checkBox_update.isChecked():
            flow_CH4 = self.mfcs[0].flow.read()['mfc_cart_CH4_flow']['value']
            self.label_CH4.setText('{:.1f} sccm'.format(flow_CH4))
            flow_CO = self.mfcs[1].flow.read()['mfc_cart_CO_flow']['value']
            self.label_CO.setText('{:.1f} sccm'.format(flow_CO))
            flow_H2 = self.mfcs[2].flow.read()['mfc_cart_H2_flow']['value']
            self.label_H2.setText('{:.1f} sccm'.format(flow_H2))

            now = ttime.time()
            timewindow = self.doubleSpinBox_timewindow.value()
            data_format= mdates.DateFormatter('%H:%M:%S')


            some_time_ago = now - 3600 * timewindow
            df = self.archiver.tables_given_times(some_time_ago, now)
            self._df_ = df


            masses = []
            for rga_mass in self.rga_masses:
                masses.append(str(rga_mass.get()))


            update_figure([self.figure_rga.ax], self.toolbar_rga, self.canvas_rga)
            for rga_ch, mass in zip(self.rga_channels, masses):
                dataset = df[rga_ch.name]
                indx = rga_ch.name[-1]
                if getattr(self, f'checkBox_rga{indx}').isChecked():
                    # put -5 in the winter, -4 in the summer
                    self.figure_rga.ax.plot(dataset['time']+timedelta(hours=-5),dataset['data'], label = f'{mass} amu')
            self.figure_rga.ax.grid(alpha=0.4)
            self.figure_rga.ax.xaxis.set_major_formatter(data_format)
            self.figure_rga.ax.set_xlim(ttime.ctime(some_time_ago), ttime.ctime(now))
            self.figure_rga.ax.autoscale_view(tight=True)
            self.figure_rga.ax.set_yscale('log')
            self.figure_rga.tight_layout()
            self.figure_rga.ax.legend(loc=6)
            self.canvas_rga.draw_idle()

            # update_figure([self.figure_temp.ax], self.toolbar_temp, self.canvas_temp)
            # if self.radioButton_current_control.isChecked():
            #     dataset1 = df[self.temps[0].name]
            #     dataset2 = df[self.temps_sp[0].name]
            # else:
            #     dataset1 = df[self.temps[1].name]
            #     dataset2 = df[self.temps_sp[1].name]
            #
            # XLIM = [dataset1['time'].iloc[0] + timedelta(hours=-4),
            #         dataset1['time'].iloc[-1] + timedelta(hours=-4)]
            #
            # self.figure_temp.ax.plot(dataset1['time'] + timedelta(hours=-4), dataset1['data'], label='T readback')
            # self.figure_temp.ax.plot(dataset2['time'] + timedelta(hours=-4), dataset2['data'], label='T setpoint')
            # if self.plot_program:
            #     if self.program_plot_moving_flag:
            #         self.update_plot_program_data()
            #     self.figure_temp.ax.plot(self.program_dataset['time'],
            #                              self.program_dataset['data'], 'k:', label='T program')
            #     XLIM[1] = np.max([self.program_dataset['time'].iloc[-1], dataset1['time'].iloc[-1] + timedelta(hours=-4)])
            #
            #
            # self.figure_temp.ax.xaxis.set_major_formatter(data_format)
            # self.figure_temp.ax.set_xlim(XLIM)
            # self.figure_temp.ax.relim(visible_only=True)
            # self.figure_temp.ax.grid(alpha=0.4)
            # self.figure_temp.ax.autoscale_view(tight=True)
            # self.figure_temp.tight_layout()
            # self.figure_temp.ax.legend(loc=5)
            # self.canvas_temp.draw_idle()

            # Check rector/exhaust status
            for indx_ch in range(2):
                for outlet in  ['reactor', 'exhaust']:
                    status_label = getattr(self, f'label_ch{indx_ch + 1}_{outlet}_status')

                    if self.ghs['channels'][f'{indx_ch + 1}'][outlet].get():
                        status_label.setStyleSheet('background-color: rgb(0,255,0)')
                    else:
                        status_label.setStyleSheet('background-color: rgb(255,0,0)')



                for indx_mnf in range(8):
                    mfc_sp_object = getattr(self, f'spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp')
                    value = "{:.2f} sccm".format(self.ghs['channels'][f'{indx_ch+1}'][f'mfc{indx_mnf+1}_rb'].get())
                    getattr(self, f'label_ch{indx_ch+1}_mnf{indx_mnf+1}_mfc_rb').setText(value)

                    mfc_sp_object = getattr(self, f'spinBox_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_sp')
                    st = mfc_sp_object.blockSignals(True)
                    value = self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_sp'].get()
                    mfc_sp_object.setValue(value)
                    mfc_sp_object.blockSignals(st)

                    sp =  self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_sp'].get()
                    rb =  self.ghs['channels'][f'{indx_ch+1}'][f'mfc{indx_mnf+1}_rb'].get()
                    status_label = getattr(self, f'label_ch{indx_ch+1}_mnf{indx_mnf+1}_mfc_status')

                    #Check if the setpoints and readbacks are close
                    if sp > 0:
                        error = np.abs((rb - sp)/sp)
                        if error > 0.1:
                            status_label.setStyleSheet('background-color: rgb(255,0,0)')
                        elif error > 0.02:
                            status_label.setStyleSheet('background-color: rgb(255,240,24)')
                        else:
                            status_label.setStyleSheet('background-color: rgb(0,255,0)')
                    else:
                        status_label.setStyleSheet('background-color: rgb(171,171,171)')










    def set_mfc_cart_flow(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        value = sender_object.value()
        mfc_dict = {'spinBox_CH4': self.mfcs[0],
                    'spinBox_CO': self.mfcs[1],
                    'spinBox_H2': self.mfcs[2],
                    }

        mfc_dict[sender_name].flow.put(value)


    def visualize_program(self):
        if self.program_sps is None:
            self.read_program_data()
        self.program_plot_moving_flag = True
        self.update_status()



    def read_program_data(self):
        print('Starting the Temperature program')
        table = self.tableWidget_program
        nrows = table.rowCount()
        times = []
        temps = []
        for i in range(nrows):
            this_time = table.item(i, 1)
            this_temp = table.item(i, 0)

            if this_time and this_temp:
                try:
                    times.append(float(this_time.text()))
                except:
                    message_box('Error', 'Time must be numerical')
                    raise ValueError('time must be numerical')
                try:
                    temps.append(float(this_temp.text()))
                except:
                    message_box('Error', 'Temperature must be numerical')
                    raise ValueError('Temperature must be numerical')

        times = np.hstack((0, np.array(times))) * 60
        temps = np.hstack((self.temps[0].get(), np.array(temps)))
        print('times', times, 'temperatures', temps)
        self.program_time = np.arange(times[0], times[-1] + self.program_update_time, self.program_update_time)

        self.program_sps = np.interp(self.program_time, times, temps)
        self.plot_program = True
        self.update_plot_program_data()




    def start_program(self):
        if self.program_sps is None:
            self.read_program_data()
        self.program_plot_moving_flag = False

        self.program_idx = 0
        self.init_time = ttime.time()
        self.RE(bps.mv(self.heater_enable1, 1))
        self.timer_program.start()


        # for this_time, this_temp in zip(times, temps):
        #     self.init_time = ttime.time()
        #     init_temp =  self.temps[0].get()
        #     self.a = (this_temp-init_temp)/this_time
        #     self.b = this_temp
        #     self.timer_program.start()
        #     while self.temps[0].get() - 7

    def update_plot_program_data(self):
        datetimes = [datetime.fromtimestamp(i).strftime('%Y-%m-%d %H:%M:%S') for i in
                     (ttime.time() + self.program_time)]
        self.program_dataset = pd.DataFrame({'time': pd.to_datetime(datetimes, format='%Y-%m-%d %H:%M:%S'),
                                             'data': self.program_sps})



    def update_temp_sp(self):
        current_time = ttime.time()
        try:
            this_sp = self.program_sps[self.program_idx]
        except IndexError:
            this_sp = self.program_sps[-1]
            self.timer_program.stop()
        print('time passed:', current_time - self.init_time, 'index:', self.program_idx, 'setpoint:', this_sp)

        # self.temps_sp[0].put(this_sp)
        self.program_idx += 1

    def toggle_exhaust_reactor(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        ch_num = sender_name[14]
        if sender_name.endswith('exhaust') and sender_object.isChecked():
            self.ghs['channels'][ch_num]['exhaust'].set(1)
            ttime.sleep(2)
            self.ghs['channels'][ch_num]['reactor'].set(0)
        if sender_name.endswith('reactor') and sender_object.isChecked():
            self.ghs['channels'][ch_num]['reactor'].set(1)
            ttime.sleep(2)
            self.ghs['channels'][ch_num]['exhaust'].set(0)


    def select_gases(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        gas = sender_object.currentText()
        #print(sender_name)
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        gas_command = self.ghs['manifolds'][indx_mnf]['gases'][gas]
        #print(f'Gas command {gas_command}')
        self.ghs['manifolds'][indx_mnf]['gas_selector'].set(gas_command)


    def toggle_channels(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()

        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        if sender_object.isChecked():
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_upstream'].set(1)
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_dnstream'].set(1)
        else:
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_upstream'].set(0)
            self.ghs['channels'][indx_ch][f'mnf{indx_mnf}_vlv_dnstream'].set(0)


    def set_flow_rates(self):
        sender = QObject()
        sender_object = sender.sender()
        sender_name = sender_object.objectName()
        #print(sender_name)
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        value = sender_object.value()
        self.ghs['channels'][indx_ch][f'mfc{indx_mnf}_sp'].set(value)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main = GUI()
    main.show()

    sys.exit(app.exec_())



