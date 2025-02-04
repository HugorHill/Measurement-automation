# keysightAWG.py
# Gleb Fedorov <vdrhc@gmail.com>
# Alexander Korenkov <soyer94_44@mail.ru>
# Alexey Dmitriev <dmitrmipt@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# TODO: reformat file docstrings

# Standard library imports
# ------------------
# Third party imports
import numpy as np
import visa

# Local application imports
# ---------------
from drivers.BiasType import BiasType


def format_e(n):
    a = '%e' % n
    return a.split('e')[0].rstrip('0').rstrip('.') + 'e' + a.split('e')[1]


class YokogawaGS210:
    """
    The driver for the Yokogawa_GS210. Default operation regime is CURRENT source.

        CURRENT SOURCE
        Source Range    Range Generated     Resolution      Max. Load Voltage
        1 mA            ±1.20000 mA         10 nA           ±30 V
        10 mA           ±12.0000 mA         100 nA          ±30 V
        100 mA          ±120.000 mA         1 μA            ±30 V
        200 mA          ±200.000 mA         1 μA            ±30 V

        VOLTAGE SOURCE
        Source Range    Range Generated     Resolution      Max. Load Current
        10 mV           ±12.0000 mV         100 nV          --------
        100 mV          ±120.000 mV         1 μV            --------
        1 V             ±1.20000 V          10 μV           ±200 mA
        10 V            ±12.0000 V          100 μV          ±200 mA
        30 V            ±32.000 V           1 mV            ±200 mA
    """

    current_ranges_supported = [.001, .01, .1, .2]           #possible current ranges supported by current source
    voltage_ranges_supported = [.01, .1, 1, 10, 30]

    def __init__(self, address, volt_compliance=3, current_compliance=.01):
        """Create a default Yokogawa_GS210 object as a current source"""
        self._address = address
        rm = visa.ResourceManager()
        self._visainstrument = rm.open_resource(self._address)

        current_range = (-200e-3, 200e-3)
        voltage_range = (-32, 32)

        self._mincurrent = -10e-3
        self._maxcurrent =  10e-3

        self._minvoltage = -1e-6
        self._maxvoltage =  1e-6

        self.current: np.float64 = None
        self.current_compliance: np.float64 = None
        self.voltage: np.float64 = None
        self.voltage_compliance: np.float64 = None
        self.status: np.int64 = None
        self.range: np.float64 = None

        self._visainstrument.write(":SOUR:FUNC CURR")

        self.set_voltage_compliance(volt_compliance)
        self.set_current(0)
        self.set_status(1)
        self._bias_type = BiasType.CURRENT

    def get_id(self):
        """Get basic info on device"""
        return self._visainstrument.query("*IDN?")

    def set_current(self, current):
        """Set current"""
        if self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n":
            print("Tough luck, mode is voltage source, cannot set current.")
            return False
        else:
            if self._mincurrent <= current <= self._maxcurrent:
                self._visainstrument.write("SOUR:LEVEL %e"%current)
                self._visainstrument.query("*OPC?")
            # else:
                # print("Error: current limits,",(self._mincurrent, self._maxcurrent)," exceeded.")

    def get_current(self):
        """Get current"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n"):
            print("Tough luck, mode is voltage source, cannot get current.")
            return False
        return float(self._visainstrument.query("SOUR:LEVEL?"))

    def set_voltage(self, voltage):
        """Set voltage"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "CURR\n"):
            print("Tough luck, mode is current source, cannot get voltage.")
            return False
        else:
             self._visainstrument.write("SOUR:LEVEL %e"%voltage)

    def get_voltage(self):
        """Get voltage"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "CURR\n"):
            print("Tough luck, mode is current source, cannot get voltage.")
            return False
        return float(self._visainstrument.query("SOUR:LEVEL?"))

    def set_status(self, status):
        """
        Turn output on and off

        Parameters:
        -----------
            status: 0 or 1
                0 for off, 1 for on
        """
        self._visainstrument.write("OUTP "+("ON" if status==1 else "OFF"))

    def get_status(self):
        """Check if output is turned on"""
        return self._visainstrument.query("OUTP?")

    def get_voltage_compliance(self):
        """Get compliance voltage"""
        return float(self._visainstrument.query("SOUR:PROT:VOLT?"))

    def set_voltage_compliance(self, compliance):
        """Set compliance voltage"""
        if self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n":
            print("Tough luck, mode is voltage source, cannot set voltage "
                  "compliance.")
            return False
        self._visainstrument.write("SOUR:PROT:VOLT %e"%compliance)

    def get_current_compliance(self):
        """Get compliance voltage"""
        return float(self._visainstrument.query("SOUR:PROT:CURR?"))

    def set_current_compliance(self, compliance):
        """Set compliance current"""
        if self._visainstrument.query(":SOUR:FUNC?") == "CURR\n":
            print("Tough luck, mode is current source, cannot set current compliance.")
            return False
        self._visainstrument.write("SOUR:PROT:CURR %e"%compliance)

    def get_range(self):
        """Get current range in A"""
        currange = self._visainstrument.query("SOUR:RANG?")[:-1]
        return -float(currange), float(currange)

    def set_range(self, maxval):
        """Set current range in A"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "CURR\n"):
            if not (maxval in self.current_ranges_supported):
                print("Given current range is invalid. Please enter valid current range in !!!Amperes!!!\nValid ranges are (in A): {0}".format(self.current_ranges_supported))
                return False
            else:
                self._mincurrent = -maxval
                self._maxcurrent = maxval
                self._visainstrument.write("SOUR:RANG %e"%maxval)
        if(self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n"):
            if not (maxval in self.voltage_ranges_supported):
                print("Given voltage range is invalid. Please enter valid voltage range in !!!Volts!!!\nValid ranges are (in A): {0}".format(self.voltage_ranges_supported))
                return False
            else:
                self._minvoltage = -maxval
                self._maxvoltage = maxval
                self._visainstrument.write("SOUR:RANG %e"%maxval)

    def set_appropriate_range(self, max_bias=1E-3, min_bias=-1E-3):
        """Detect which range includes limits and set it"""
        if self._bias_type == BiasType.CURRENT:
            required_current = max(abs(max_bias), abs(min_bias))
            for current_range in self.current_ranges_supported:
                if current_range >= required_current:
                    self.set_range(current_range)
                    return True
                if(current_range == self.current_ranges_supported[-1]):
                    print("Current is too big, can't handle it!")
                    return False
        else:
            required_voltage = max(abs(max_bias), abs(min_bias))
            for voltage_range in self.voltage_ranges_supported:
                if voltage_range >= required_voltage:
                    self.set_range(voltage_range)
                    return True
                if (voltage_range == self.voltage_ranges_supported[-1]):
                    print("Current is too big, can't handle it!")
                    return False


    def set_src_mode_volt(self):
        """
        Changes mode from current to voltage source, compliance current is given as an argument

        Returns:
            True if the mode was changed, False otherwise
        """
        if self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n":
            return False
        else:
            self._bias_type = BiasType.VOLTAGE
            self._visainstrument.write(":SOUR:FUNC VOLT")
            self.set_status(1)
            return True

    def set_src_mode_curr(self):
        """
        Changes mode from voltage to current source, compliance voltage is given as an argument

        Returns:
            True if the mode was changed, False otherwise
        """
        if self._visainstrument.query(":SOUR:FUNC?") == "CURR\n":
            return False
        else:
            self._bias_type = BiasType.CURRENT
            self._visainstrument.write(":SOUR:FUNC CURR")
            self.set_status(1)
            return True

    # TODO: pending to delete this function
    def set_current_limits(self, mincurrent = -1E-3, maxcurrent = 1E-3):
        """ Sets a limits within the range if needed for safe sweeping"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "CURR\n"):
            if mincurrent >= -1.2*self.get_range():
                   self._mincurrent = mincurrent
            else:
                print("Too low mincurrent queryed to set.")
            if maxcurrent <= 1.2*self.get_range():
                self._maxcurrent = maxcurrent
            else:
                print("Too high maxcurrent queryed to set.")
        else:
            print("Go in current mode first.")

    # TODO: pending to delete this function
    def set_voltage_limits(self, minvoltage = -1E-3, maxvoltage = 1E-3):
        """ Sets a voltage limits within the range if needed for safe sweeping"""
        if (self._visainstrument.query(":SOUR:FUNC?") == "VOLT\n"):
            if minvoltage >= -1*self.get_range():
                   self._minvoltage = minvoltage
            else:
                print("Too low minvoltage queryed to set.")
            if maxvoltage <= self.get_range():
                self._maxvoltage = maxvoltage
            else:
                print("Too high maxvoltage asked to set.")
        else:
            print("Go in voltage mode first.")

    def clear(self):
        """
        Clear the event register, extended event register, and error queue.
        """
        self._visainstrument.write("*CLS")

    def get_bias_type(self):
        return self._bias_type

    def set(self, parameter):
        if self._bias_type is BiasType.VOLTAGE:
            self.set_voltage(parameter)
        else:
            self.set_current(parameter)
