from unittest.mock import Mock

import pandas as pd
import pytest
from PyQt5 import QtCore

from iss_xsample.gas_type import GasType
from iss_xsample.xsample import XsampleGui


def test_gas_selection_can_be_edited_and_unchecked(qtbot):
    widget = GasType(gas_name="He")
    qtbot.addWidget(widget)
    widget.checkBox_select_gas.setChecked(True)
    widget.lineEdit_gas_setpoint.setText("12.5")
    widget.read_gas_flow()
    assert widget.gas_list_with_flow == ["He at 12.5 sccm"]
    widget.add_selected_gas()
    assert len(widget.gas_list_with_flow) == 1
    widget.checkBox_select_gas.setChecked(False)
    assert widget.gas_list_with_flow == []


def test_missing_hardware_reports_configuration_error(qapp):
    with pytest.raises(ValueError, match="Missing beamline configuration"):
        XsampleGui()


def test_cart_valve_emits_one_command(gui):
    gui.RE.reset_mock()
    checkbox = gui.checkBox_cart_vlv1
    checkbox.setChecked(not checkbox.isChecked())
    gui.RE.assert_called_once()


def test_bulk_resize_does_not_recalculate_cells(gui, qtbot):
    changed = Mock()
    gui.tableWidget_program.cellChanged.connect(changed)
    gui.spinBox_steps.setValue(4)
    assert gui.tableWidget_program.columnCount() == 4
    assert gui.tableWidget_program.item(3, 3).text() == "0"
    changed.assert_not_called()


def test_workbook_load_preserves_program_values_and_directions(
    gui, program_steps, tmp_path
):
    gui.process_program_steps = program_steps
    path = tmp_path / "program.xlsx"
    gui.create_dataframe().to_excel(path)
    changed = Mock()
    gui.tableWidget_program.cellChanged.connect(changed)
    gui.create_table_using_xlsx_file(path)
    assert gui.spinBox_steps.value() == 2
    assert gui.tableWidget_program.item(1, 0).text() == "10.0"
    assert gui.tableWidget_program.item(2, 0).text() == "2.5"
    assert gui.tableWidget_program.item(3, 0).checkState() == QtCore.Qt.Checked
    assert gui.tableWidget_program.item(3, 1).checkState() == QtCore.Qt.Unchecked
    changed.assert_not_called()
    gui.create_gas_program_dict()
    assert gui.process_program_steps[1]["flow_1"] == program_steps[1]["flow_1"]


def test_cancel_save_does_not_write(gui, monkeypatch):
    monkeypatch.setattr(
        "iss_xsample.xsample.QtWidgets.QFileDialog.getSaveFileName",
        lambda *args: ("", ""),
    )
    write = Mock()
    monkeypatch.setattr(pd.DataFrame, "to_excel", write)
    gui.save_gas_program()
    write.assert_not_called()


def test_plotting_accepts_empty_temperature_data(gui):
    empty = pd.DataFrame(
        {"time": pd.Series(dtype="datetime64[ns]"), "data": pd.Series(dtype=float)}
    )
    gui._df_ = {"temp2": empty, "temp2_sp": empty}
    for channel in range(1, 3):
        for mfc in range(1, 9):
            gui._df_[f"ghs_ch{channel}_mfc{mfc}_rb"] = empty
    for gas in ("CH4", "CO", "H2"):
        gui._df_[f"mfc_cart_{gas}_rb"] = empty
    gui.now = 1_800_000_000
    gui.some_time_ago = gui.now - 3600
    gui.update_plotting_status()
    assert gui._df_ is None


def test_close_stops_polling(gui):
    gui.close()
    assert not gui._archiver_poller.request(1)
    assert not gui.timer_read_archiver.isActive()
