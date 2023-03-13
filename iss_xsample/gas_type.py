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

# checkBox_ch1_mnf1_enable

from matplotlib.figure import Figure
from isstools.elements.figure_update import update_figure
from datetime import timedelta, datetime
import time as ttime
from isstools.dialogs.BasicDialogs import message_box

ui_path = pkg_resources.resource_filename('iss_xsample', 'ui/gas_type.ui')

from pandas.plotting import register_matplotlib_converters
register_matplotlib_converters()


class GasType(*uic.loadUiType(ui_path)):
    def __init__(self,
                 gas_cart = [],
                 # total_flow_meter = None,
                 # rga_channels = [],
                 rga_masses = [],
                 # heater_enable1 = [],
                 ghs = [],
                 RE = [],
                 # archiver = [],
                 gas_name = None,
                 # sample_envs_dict=[],
                 *args, **kwargs,
                 ):
        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.gas_cart = gas_cart
        self.ghs = ghs
        self.RE = RE
        # self.archiver = archiver

        self.gas_name = gas_name

        self.label_gas = QtWidgets.QLabel("")
        self.label_gas.setText(self.gas_name)
        self.gridLayout_gas_type.addWidget(self.label_gas, 0, 0)

        self.lineEdit_gas_setpoint = QtWidgets.QLineEdit("")
        self.lineEdit_gas_setpoint.setText(f"{0:2.1f} sccm")
        self.gridLayout_gas_type.addWidget(self.lineEdit_gas_setpoint, 0, 1)
        self.lineEdit_gas_setpoint.returnPressed.connect(self.read_gas_flow)

        self.label_gas_select = QtWidgets.QLabel("     ")
        self.label_gas_select.setStyleSheet('background-color: rgb(192,192,192)')
        self.gridLayout_gas_type.addWidget(self.label_gas_select, 0, 2)

        self.checkBox_select_gas = QtWidgets.QCheckBox()
        self.gridLayout_gas_type.addWidget(self.checkBox_select_gas, 0, 3)
        self.checkBox_select_gas.stateChanged.connect(self.add_selected_gas)

        self.gas_list_with_flow = []

    def read_gas_flow(self):
        _user_set_value_text = self.lineEdit_gas_setpoint.text()
        _user_set_value = float(_user_set_value_text.split()[0])
        self.lineEdit_gas_setpoint.setText(f"{_user_set_value} sccm")

    def add_selected_gas(self):
        if self.checkBox_select_gas.isChecked() == True:
            self.label_gas_select.setStyleSheet('background-color: rgb(95,249,95)')
            _user_set_value_text = self.lineEdit_gas_setpoint.text()
            self.gas_list_with_flow.append(f"{self.gas_name} at {_user_set_value_text}")
            # self.listWidget_gases.additems(self.gas_list_with_flow)
        else:
            self.label_gas_select.setStyleSheet('background-color: rgb(192,192,192)')
            self.gas_list_with_flow.pop(f"{self.gas_name} at {_user_set_value_text}")
