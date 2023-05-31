
# def save_program_data(self):
#     _saveFile = QtWidgets.QAction("&Save File", self)
#     _saveFile.setShortcut('Ctrl+S')
#     _saveFile.setStatusTip('Save File')
#     _saveFile.triggered.connect(self.file_save)
#
# def file_save(self):
#     path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save File', '/home/xf08id/Documents/xsample_program/',
#                                                     '*.xlsx')
#     print(path)
#     print(str(path))
#
#     self.create_dataframe(path)
#
# def create_dataframe(self, path):
#     param  = ['temp', 'duration', 'rate', 'flow1', 'flow2', 'flow3', 'flow4', 'flow5']
#     _ch  = [0, 0, 0]
#     _gas = [0, 0, 0]
#     for i in range(1,6):
#         if self.gas_program_steps[0]['flow_' + str(i)]:
#             _ch.append(self.gas_program_steps[0]['flow_'+str(i)]['channel'])
#             _gas.append(self.gas_program_steps[0]['flow_'+str(i)]['name'])
#         else:
#             _ch.append(0)
#             _gas.append(None)
#
#     _df = pd.DataFrame()
#     _df['param'] = param
#     _df['channel'] = _ch
#     _df['gas'] = _gas
#
#     for i, key in enumerate(self.gas_program_steps.keys()):
#         _t = []
#         _t.append(self.gas_program_steps[key]['temp'])
#         _t.append(self.gas_program_steps[key]['duration'])
#         _t.append(self.gas_program_steps[key]['rate'])
#         for j in range(1,6):
#             if self.gas_program_steps[0]['flow_' + str(j)]:
#                 _t.append(self.gas_program_steps[0]['flow_'+str(j)]['flow'])
#             else:
#                 _t.append(None)
#         _df[i+1] = _t
#
#     _df.to_excel(path + '.xlsx')
#
# def load_gas_program(self):
#     path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open File', '/home/xf08id/Documents/xsample_program/',
#                                                     '*.xlsx')
#     self.create_table_using_xlsx_file(path)
#
# def create_table_using_xlsx_file(self, path):
#     pass
#
#
#
#
#
#
#
#
#
#
# def init_table_widget(self):
#     self.manage_number_of_steps()
#     self.tableWidget_program.setVerticalHeaderLabels(('Temperature, C°', 'Duration, min','Ramp rate, C°/min',
#                                                       'Flow rate 1, sccm', 'Flow rate 2, sccm',
#                                                       'Flow rate 3, sccm', 'Flow rate 4, sccm',
#                                                       'Flow rate 5, sccm'
#                                                       ))
#
#     combo_box_options = ['None',
#                          'CH4',
#                          'CO',
#                          'H2',
#                          'He',
#                          'N2',
#                          'Ar',
#                          'O2',
#                          'CO-ch',
#                          'CO2']
#     for indx in range(5):
#         combo = getattr(self, f'comboBox_gas{indx + 1}')
#         for option in combo_box_options:
#             combo.addItem(option)
#
#
# def manage_number_of_steps(self):
#     no_of_steps = self.spinBox_steps.value()
#     self.tableWidget_program.setColumnCount(no_of_steps)
#     self.tableWidget_program.setRowCount(8)
#     self.handle_program_changes()
#
#
# def handle_program_changes(self):
#     self.gas_program_steps = {}
#     no_of_columns = self.tableWidget_program.columnCount()
#
#     _tmp = {'temp' : None,
#             'duration' : None,
#             'rate' : None,
#             'flow_1': None,
#             'flow_2' : None,
#             'flow_3' : None,
#             'flow_4' : None,
#             'flow_5' : None,
#             }
#     for col in range(no_of_columns):
#
#         def check_status_of_radioButton(channel=None):
#             if getattr(self, 'radioButton_f' + str(channel) + '_1').isChecked():
#                 return 1
#             else:
#                 return 2
#
#
#         self.gas_program_steps[col] = {}
#
#         for i, key in enumerate(['temp', 'duration', 'rate']):
#             _tmp[key] = self.tableWidget_program.item(i,col)
#             if _tmp[key]:
#                 self.gas_program_steps[col][key] = float(_tmp[key].text())
#             else:
#                 self.gas_program_steps[col][key] = None
#
#
#         for j, gas_key in enumerate(['flow_1', 'flow_2', 'flow_3', 'flow_4', 'flow_5'], start=3):
#             _tmp[gas_key] = self.tableWidget_program.item(j,col)
#
#             if _tmp[gas_key]:
#                 self.gas_program_steps[col][gas_key] = {}
#
#                 ch = check_status_of_radioButton(j-2)
#                 self.gas_program_steps[col][gas_key]['channel'] = ch
#                 self.gas_program_steps[col][gas_key]['name'] = getattr(self, 'comboBox_gas' + str(j-2)).currentText()
#                 self.gas_program_steps[col][gas_key]['flow'] = float(_tmp[gas_key].text())
#             else:
#                 self.gas_program_steps[col][gas_key] = None
#
# def manage_duration_n_rate(self):
#     previous_temp =  25
#     for i, key in enumerate(self.gas_program_steps.keys()):
#         if self.gas_program_steps[key]['temp']:
#
#             print(f"previous_temp: {previous_temp}")
#
#
#             if self.gas_program_steps[key]['duration'] and (self.gas_program_steps[key]['duration'] > 0):
#                 self.gas_program_steps[key]['rate'] = abs((self.gas_program_steps[key]['temp'] - previous_temp)/self.gas_program_steps[key]['duration'])
#
#                 print(f"rate: {self.gas_program_steps[key]['rate']}")
#
#                 item = QtWidgets.QTableWidgetItem(str(self.gas_program_steps[key]['rate']))
#                 self.tableWidget_program.setItem(2,i, item)
#                 previous_temp = self.gas_program_steps[key]['temp']
#                 continue
#             elif self.gas_program_steps[key]['rate'] and (self.gas_program_steps[key]['rate'] > 0):
#
#
#                 self.gas_program_steps[key]['duration'] = abs((self.gas_program_steps[key]['temp'] - previous_temp)/self.gas_program_steps[key]['rate'])
#
#                 print(f"duration: {self.gas_program_steps[key]['duration']}")
#
#                 item = QtWidgets.QTableWidgetItem(str(self.gas_program_steps[key]['duration']))
#                 self.tableWidget_program.setItem(1, i, item)
#                 previous_temp = self.gas_program_steps[key]['temp']
#     self.visualize_temperature_program()
#
#
#
# def read_temperature_program_data(self):
#     times = []
#     sps = []
#
#     for i, key in enumerate(self.gas_program_steps):
#         if self.gas_program_steps[i]['temp'] and self.gas_program_steps[i]['duration']:
#             times.append(self.gas_program_steps[i]['duration'])
#             sps.append(self.gas_program_steps[i]['temp'])
#
#     times = np.cumsum(times)
#     times = np.hstack((0, np.array(times))) * 60
#     sps = np.hstack((self.current_sample_env.current_pv_reading(), np.array(sps)))
#     print('The parsed program:')
#     for _time, _sp in zip(times, sps):
#         print('time', _time, '\ttemperature', _sp)
#     self.pid_program = {'times': times, 'setpoints': sps}
#
# def visualize_temperature_program(self):
#     self.read_temperature_program_data()
#     self.plot_program_flag = True
#     self.program_plot_moving_flag = True
#     self.update_plot_program_data()
#     self.update_status()
#
#
#
#
#

################## Gas program ###################

# def init_table_widget(self):
#     # TODO: make the table length correspond to the max length acceptable by the sample environment
#
#     self.tableWidget_program.setColumnCount(self.num_steps)
#     self.tableWidget_program.setRowCount(8)
#
#     self.tableWidget_program.setVerticalHeaderLabels(('Temperature, C°' , 'Ramp rate, C°/min', 'Duration, min',
#                                                       'Flow rate 1, sccm',  'Flow rate 2, sccm',
#                                                       'Flow rate 3, sccm',  'Flow rate 4, sccm',
#                                                      'Flow rate 5, sccm'
#                                                      ))
#
#     combo_box_options= ['None', 'Methane', 'CO', 'Hydrogen', 'Carbon dioxide', 'Oxygen','Helium','Nitrogen', 'Argon']
#     for indx in range(5):
#         combo = getattr(self, f'comboBox_gas{indx+1}')
#         for option in combo_box_options:
#             combo.addItem(option)
#
#     self.tableWidget_program.cellChanged.connect(self.handle_program_changes)
#
# def handle_program_changes(self, row, column):
#     def ramp_driven(column, t_range):
#         ramp_rate = int(self.tableWidget_program.item(1, column).text())
#         duration = t_range / ramp_rate
#         item = QtWidgets.QTableWidgetItem(str(duration))
#         item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
#         self.tableWidget_program.setItem(2, column, item)
#         self.setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
#         self.step_priority[column] = 1  # one is priority on ramp
#
#     def duration_driven(column, t_range):
#         duration = int(self.tableWidget_program.item(2, column).text())
#         ramp = t_range / duration
#         item = QtWidgets.QTableWidgetItem(str(ramp))
#         item.setForeground(QtGui.QBrush(QtGui.QColor(78, 190, 181)))
#         self.tableWidget_program.setItem(1, column, item)
#         self.tableWidget_program.item(2, column).setForeground(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
#         self.step_priority[column] = 2  # one is priority on duration
#
#     self.tableWidget_program.cellChanged.disconnect(self.handle_program_changes)
#     sample_env = self.current_sample_env
#     print(row, column)
#     temperature = None
#     previous_temperature = None
#     if column > 0:
#         if self.tableWidget_program.item(0, column - 1):
#             if self.tableWidget_program.item(0, column - 1).text()!= '':
#                 previous_temperature = int(self.tableWidget_program.item(0, column - 1).text())
#         if self.tableWidget_program.item(0, column):
#             temperature = int(self.tableWidget_program.item(0, column).text())
#     else:
#         previous_temperature = np.round(sample_env.pv.get())
#         previous_temperature = 25
#         if self.tableWidget_program.item(0, column):
#             if self.tableWidget_program.item(0, column).text() != '':
#                 temperature = int(self.tableWidget_program.item(0, column).text())
#     if temperature and previous_temperature:
#         t_range = temperature - previous_temperature
#         if row == 0:
#             if self.tableWidget_program.item(1, column):
#                 ramp_driven(column,t_range)
#             elif self.tableWidget_program.item(2, column):
#                 duration_driven(column,t_range)
#         if row == 1:
#             if self.tableWidget_program.item(1, column): #ramp
#                 ramp_driven(column, t_range)
#         elif row ==2:
#             if self.tableWidget_program.item(2, column): #duration
#                 duration_driven(column, t_range)
#
#
#
#
#     self.tableWidget_program.cellChanged.connect(self.handle_program_changes)


# self._gases = {}
# self.__ch1 = ["He/N<sub>2</sub>/Ar", "H<sub>2</sub>/NH<sub>3</sub>",
#                          "CH<sub>4</sub>/C<sub>2</sub>H<sub>4</sub>", "NO<sub>x</sub>/Future",
#                          "AsH<sub>3</sub>/PH<sub>3</sub>", "O<sub>2</sub>", "CO", "CO<sub>2</sub>"]
# self.__ch2 = ["He/N<sub>2</sub>/Ar", "H<sub>2</sub>/NH<sub>3</sub>",
#                          "CH<sub>4</sub>/C<sub>2</sub>H<sub>4</sub>", "NO<sub>x</sub>/Future",
#                          "AsH<sub>3</sub>/PH<sub>3</sub>"]
# self.__ch3 = ["Methane", "CO", "H<sub>2</sub>"]
#
# self._gases['ch1'] = dict(zip(np.arange(1,8,1), self.__ch1))
# self._gases['ch2'] = dict(zip(np.arange(1,6,1), self.__ch2))
# self._gases['ch3'] = dict(zip(np.arange(1,4,1), self.__ch3))
#
# for i in range(1,4):
#     for gas in self._gases['ch'+str(i)].values():
#         getattr(self, f"verticalLayout_gases_ch{i}").addWidget(GasType(self.gas_cart,
#                                                                         self.ghs,
#                                                                         # self.archiver,
#                                                                         gas_name=gas))

# self.pushButton_add_gases.clicked.connect(self.update_gas_list)


# def update_gas_list(self):
#     print(self.)
# j = 0
# for i in range(len(self.ghs['manifolds'])):
#     for key in self.ghs['manifolds'][str(i+1)]['gases'].keys():
#         self.gas_label = QtWidgets.QLabel("")
#         self.gas_label.setText(key)
#         self.gridLayout_gases.addWidget(self.gas_label, j, 0)
#
#         self.gas_setpoint = QtWidgets.QLineEdit("")
#         self.gas_setpoint.setText(f"{0:2.1f} sccm")
#         self.gridLayout_gases.addWidget(self.gas_setpoint, j, 1)
#         self.gas_setpoint.returnPressed.connect(self.read_gas_flow)
#
#         self.gas_check_box = QtWidgets.QCheckBox()
#         self.gridLayout_gases.addWidget(self.gas_check_box, j, 2)
#         # if self.gas_check_box.isChecked:
#         j += 1

# def read_gas_flow(self):
#     _user_set_value_text = self.gas_setpoint.text()
#     print(_user_set_value_text)
#     _user_set_value = float(_user_set_value_text.split()[0])
#     print(_user_set_value)
#     self.gas_setpoint.setText(f"{_user_set_value} sccm")
ks = x.gas_program_steps.keys()
gas_program = {}

gas_list= []
first_step = x.gas_program_steps[0]
for j in range(1, 6):
    gas = first_step[f'flow_{j}']['name']
    print(j, gas)
    if gas != 'None':
        gas_program[gas] = []
        for steps in x.gas_program_steps.keys()
            gas_program[gas].append(x.gas_program_steps[steps]['flow_' +str()])


total_duration = 0
gases = list(gas_program.keys())

for k in ks:
    step = x.gas_program_steps[k]
    total_duration += step['duration']
    for j in range(1, 6):
        gas = first_step[f'flow_{j}']['name']
        if gas in gases:



print(total_duration)


df = x.create_dataframe()
for indx in range(3,8):
    print(df.iloc[indx])
    if f.iloc[indx]['gas'] != None

for k in ks:
    step = x.gas_program_steps[k]
    for j in range(1, 6):
        if step[f'flow_{j}'] is not None:
            if step[f'flow_{j}']['name'] != 'None':
                print(step[f'flow_{j}']['name'])


for indx in range(3,8):
    print(df.iloc[indx])
    if df.iloc[indx]['gas'] == 'None':
        df.drop[indx]


temp = list(df.loc[0][3:])
temp.insert(0,0)
duration = list(df.loc[1][3:])
duration.insert(0,0)

flows = {}
for indx in range(3,8):
    if df.loc[indx]['gas'] !='None':
        times = list(df.loc[indx][3:])
        times.insert(0,0)
        flows[df.loc[indx]['gas']] = times

plt.figure();
for k  in flows.keys():
    plt.step(np.cumsum(duration),flows[k], label=k)
    plt.legend()


from PyQt5 import QtGui, QtWidgets, QtCore, uic
for step in range(1, no_of_steps + 1):
    for i, value in enumerate(_df[step]):
        item = QtWidgets.QTableWidgetItem(str(value))
        x.tableWidget_program.setItem(i, step - 1, item)




