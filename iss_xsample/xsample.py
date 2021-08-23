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
                 heater_enable1 = [],
                 ghs = [],
                 RE = [],
                 archiver = [],
                 sample_envs_dict=[],
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.addCanvas()
        self.mfcs = mfcs
        self.rga_channels = rga_channels
        self.rga_masses = rga_masses
        self.ghs = ghs

        self.sample_envs_dict = sample_envs_dict

        self.RE = RE
        self.archiver = archiver

        self.push_visualize_program.clicked.connect(self.visualize_program)
        self.push_clear_program.clicked.connect(self.clear_program)
        self.push_start_program.clicked.connect(self.start_program)
        self.push_pause_program.setChecked(0)
        self.push_pause_program.toggled.connect(self.pause_program)
        self.push_stop_program.clicked.connect(self.stop_program)

        self.pid_program = None
        self.plot_program_flag = False
        self.program_plot_moving_flag = True
        self._plot_program_data = None

        sample_envs_list = [k for k in self.sample_envs_dict.keys()]
        self.comboBox_sample_envs.addItems(sample_envs_list)
        self.comboBox_sample_envs.currentIndexChanged.connect(self.sample_env_selected)
        self.sample_env_selected()

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

        for indx_mfc in range(3):
            mfc_widget = getattr(self, f'spinBox_cart_mfc{indx_mfc+1}_sp')
            mfc_widget.setValue(self.mfcs[indx_mfc].sp.get())
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

            # set signal handling of gas selector widgets
            for indx_mnf in range(5):
                gas_selector_widget = getattr(self,f'comboBox_ch{indx_ch+1}_mnf{indx_mnf+1}_gas')
                gas = self.ghs['manifolds'][f'{indx_mnf+1}']['gas_selector'].get()
                gas_selector_widget.setCurrentIndex(self.gas_mapper[f'{indx_mnf+1}'][gas])
                gas_selector_widget.currentIndexChanged.connect(self.select_gases)
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
                mfc_sp_object.editingFinished.connect(self.set_flow_rates)


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


    def sample_env_selected(self):
        _current_key = self.comboBox_sample_envs.currentText()
        self.current_sample_env = self.sample_envs_dict[_current_key]
        self.init_table_widget()

    def init_table_widget(self):
        # TODO: make the table length correspond to the max length acceptable by the sample environment
        self.tableWidget_program.setColumnCount(2)
        self.tableWidget_program.setRowCount(10)
        setpoint_name = f'{self.current_sample_env.pv_name}\nsetpoint ({self.current_sample_env.pv_units})'
        self.tableWidget_program.setHorizontalHeaderLabels(('Time (min)', setpoint_name))



    def update_ghs_status(self):
        # update card MFC setpoints and readbacks
        for indx_mfc in range(3):
            mfc_rb_widget = getattr(self, f'spinBox_cart_mfc{indx_mfc + 1}_rb')
            rb = '{:.1f} sccm'.format(self.mfcs[indx_mfc].rb.get())
            mfc_rb_widget.setText(rb)
            mfc_sp_widget = getattr(self, f'spinBox_cart_mfc{indx_mfc + 1}_sp')
            st = mfc_sp_widget.blockSignals(True)
            sp = self.mfcs[indx_mfc].sp.get()
            if not mfc_sp_widget.hasFocus():
                mfc_sp_widget.setValue(sp)
            mfc_sp_widget.blockSignals(st)

            # Check if the setpoints and readbacks are close
            status_label = getattr(self, f'label_cart_mfc{indx_mfc + 1}_status')
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
                value = "{:.2f} sccm".format(self.ghs['channels'][f'{indx_ch + 1}'][f'mfc{indx_mnf + 1}_rb'].get())
                getattr(self, f'label_ch{indx_ch + 1}_mnf{indx_mnf + 1}_mfc_rb').setText(value)

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
                        status_label.setStyleSheet('background-color: rgb(255,0,0)')
                    elif error > 0.02:
                        status_label.setStyleSheet('background-color: rgb(255,240,24)')
                    else:
                        status_label.setStyleSheet('background-color: rgb(0,255,0)')
                else:
                    status_label.setStyleSheet('background-color: rgb(171,171,171)')


    def update_sample_env_status(self):
        sample_env = self.current_sample_env
        self.label_pv_rb.setText(f'{sample_env.pv_name} RB: {np.round(sample_env.pv.get(), 2)}')
        self.label_pv_sp.setText(f'{sample_env.pv_name} SP: {np.round(sample_env.pv_sp.get(), 2)}')
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


    def update_plotting_status(self):
        now = ttime.time()
        timewindow = self.doubleSpinBox_timewindow.value()
        data_format = mdates.DateFormatter('%H:%M:%S')

        some_time_ago = now - 3600 * timewindow
        df = self.archiver.tables_given_times(some_time_ago, now)
        self._df_ = df
        self._xlim_num = [some_time_ago, now]
        # handling the xlim extension due to the program vizualization
        if self.plot_program_flag:
            if self._plot_program_data is not None:
                self._xlim_num[1] = np.max([self._plot_program_data['time_s'].iloc[-1], self._xlim_num[1]])
        _xlim = [ttime.ctime(self._xlim_num[0]), ttime.ctime(self._xlim_num[1])]

        masses = []
        for rga_mass in self.rga_masses:
            masses.append(str(rga_mass.get()))

        update_figure([self.figure_rga.ax], self.toolbar_rga, self.canvas_rga)
        for rga_ch, mass in zip(self.rga_channels, masses):
            dataset = df[rga_ch.name]
            indx = rga_ch.name[-1]
            if getattr(self, f'checkBox_rga{indx}').isChecked():
                # put -5 in the winter, -4 in the summer
                self.figure_rga.ax.plot(dataset['time'] + timedelta(hours=-4), dataset['data'], label=f'{mass} amu')
        self.figure_rga.ax.grid(alpha=0.4)
        self.figure_rga.ax.xaxis.set_major_formatter(data_format)
        self.figure_rga.ax.set_xlim(_xlim)
        self.figure_rga.ax.autoscale_view(tight=True)
        self.figure_rga.ax.set_yscale('log')
        self.figure_rga.tight_layout()
        self.figure_rga.ax.legend(loc=6)
        self.canvas_rga.draw_idle()

        update_figure([self.figure_temp.ax], self.toolbar_temp, self.canvas_temp)

        dataset_rb = df['temp2']
        dataset_sp = df['temp2_sp']
        dataset_sp = self._pad_dataset_sp(dataset_sp, dataset_rb['time'].values[-1])

        self.figure_temp.ax.plot(dataset_sp['time'] + timedelta(hours=-4), dataset_sp['data'], label='T setpoint')
        self.figure_temp.ax.plot(dataset_rb['time'] + timedelta(hours=-4), dataset_rb['data'], label='T readback')
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


    def read_program_data(self):
        table = self.tableWidget_program
        nrows = table.rowCount()
        times = []
        sps = [] # setpoints
        for i in range(nrows):
            this_time = table.item(i, 0)
            this_sp = table.item(i, 1)

            if this_time and this_sp:
                try:
                    times.append(float(this_time.text()))
                except:
                    message_box('Error', 'Time must be numerical')
                    raise ValueError('time must be numerical')
                try:
                    sps.append(float(this_sp.text()))
                except:
                    message_box('Error', 'Temperature must be numerical')
                    raise ValueError('Temperature must be numerical')

        times = np.hstack((0, np.array(times))) * 60
        sps = np.hstack((self.current_sample_env.current_pv_reading(), np.array(sps)))
        print('The parsed program:')
        for _time, _sp in zip(times, sps):
            print('time', _time, '\ttemperature', _sp)
        self.pid_program = {'times' : times, 'setpoints' : sps}

    def visualize_program(self):
        self.read_program_data()
        self.plot_program_flag = True
        self.program_plot_moving_flag = True
        self.update_plot_program_data()
        self.update_status()


    def update_plot_program_data(self):
        if self.pid_program is not None:
            times = (ttime.time() + self.pid_program['times'])
            datetimes = [datetime.fromtimestamp(i).strftime('%Y-%m-%d %H:%M:%S') for i in times]
            self._plot_program_data = pd.DataFrame({'time': pd.to_datetime(datetimes, format='%Y-%m-%d %H:%M:%S'),
                                                    'data': self.pid_program['setpoints'],
                                                    'time_s' : times})


    def plot_pid_program(self):
        if self.plot_program_flag:
            if self.program_plot_moving_flag:
                self.update_plot_program_data()
            if self._plot_program_data is not None:
                self.figure_temp.ax.plot(self._plot_program_data['time'],
                                         self._plot_program_data['data'], 'k:', label='Program Viz')


    def clear_program(self):
        self.tableWidget_program.clear()
        self.init_table_widget()
        self.plot_program_flag = False
        self.program_plot_moving_flag = False
        self._plot_program_data = None
        self.pid_program = None
        self.update_status()


    def start_program(self):
        # if self.pid_program is None:
        #     self.read_program_data()
        self.visualize_program()
        self.program_plot_moving_flag = False
        self.current_sample_env.ramp_start(self.pid_program['times'].tolist(),
                                           self.pid_program['setpoints'].tolist())

    def pause_program(self, value):
        if value == 1:
            self.current_sample_env.ramp_pause()
        else:
            self.current_sample_env.ramp_continue()

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
        self.mfcs[indx_mfc - 1].sp.set(value)


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
        # print(sender_name)
        indx_ch, indx_mnf = re.findall(r'\d+', sender_name)
        value = sender_object.value()
        self.ghs['channels'][indx_ch][f'mfc{indx_mnf}_sp'].set(value)





if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main = GUI()
    main.show()

    sys.exit(app.exec_())
