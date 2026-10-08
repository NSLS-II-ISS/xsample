"""Gas selection widget."""

from importlib.resources import as_file, files

from PyQt5 import QtWidgets, uic

with as_file(files("iss_xsample").joinpath("ui/gas_type.ui")) as ui_path:
    _UiForm, _UiBase = uic.loadUiType(str(ui_path))


class GasType(_UiForm, _UiBase):
    def __init__(
        self,
        gas_cart=None,
        rga_masses=None,
        ghs=None,
        RE=None,
        gas_name=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.gas_cart = gas_cart
        self.ghs = ghs
        self.RE = RE

        self.gas_name = gas_name

        self.label_gas = QtWidgets.QLabel("")
        self.label_gas.setText(self.gas_name)
        self.gridLayout_gas_type.addWidget(self.label_gas, 0, 0)

        self.lineEdit_gas_setpoint = QtWidgets.QLineEdit("")
        self.lineEdit_gas_setpoint.setText(f"{0:2.1f} sccm")
        self.gridLayout_gas_type.addWidget(self.lineEdit_gas_setpoint, 0, 1)
        self.lineEdit_gas_setpoint.returnPressed.connect(self.read_gas_flow)

        self.label_gas_select = QtWidgets.QLabel("     ")
        self.label_gas_select.setStyleSheet("background-color: rgb(192,192,192)")
        self.gridLayout_gas_type.addWidget(self.label_gas_select, 0, 2)

        self.checkBox_select_gas = QtWidgets.QCheckBox()
        self.gridLayout_gas_type.addWidget(self.checkBox_select_gas, 0, 3)
        self.checkBox_select_gas.stateChanged.connect(self.add_selected_gas)

        self.gas_list_with_flow = []

    def read_gas_flow(self):
        _user_set_value_text = self.lineEdit_gas_setpoint.text()
        _user_set_value = float(_user_set_value_text.split()[0])
        self.lineEdit_gas_setpoint.setText(f"{_user_set_value} sccm")
        self.add_selected_gas()

    def add_selected_gas(self):
        self.gas_list_with_flow.clear()
        if self.checkBox_select_gas.isChecked():
            self.label_gas_select.setStyleSheet("background-color: rgb(95,249,95)")
            self.gas_list_with_flow.append(
                f"{self.gas_name} at {self.lineEdit_gas_setpoint.text()}"
            )
        else:
            self.label_gas_select.setStyleSheet("background-color: rgb(192,192,192)")
