def test_one_plus_one_is_two():
    "Check that one and one are indeed two."
    assert 1 + 1 == 2


class GasManager(object):
    def __init__(self, mfc=None, flow=None):
        self.mfc = mfc
        self.flow = flow



class TemperatureRampManager(object):
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

