from lib.iq_mixer_calibration import *
from lib.data_management import *
from lib2.DispersiveHahnEcho import DispersiveHahnEcho
from lib2.ReadoutExcitationShiftCalibration import \
    ReadoutExcitationShiftCalibration
from lib2.fulaut.ACStarkRunnner import ACStarkRunner

from lib2.fulaut.ResonatorOracle import *
from lib2.fulaut.STSRunner import *
from lib2.fulaut.TTSRunner import *
from lib2.DispersiveRabiOscillations import DispersiveRabiOscillations
from lib2.DispersiveRamsey import DispersiveRamsey
from lib2.DispersiveDecay import DispersiveDecay
from lib2.TwoToneSpectroscopy import *
from loggingserver import LoggingServer

from log.LogName import LogName


class MeasurementRunner:

    def __init__(self, sample_name, s_parameter, devs_aliases_map):


        self._logger = LoggingServer.getInstance(LogName.NAME)

        self._sample_name = sample_name
        self._s_parameter = s_parameter
        self._qubit_names = "I II III IV V VI VII VIII".split(" ")
        self._res_limits = {}
        self._sts_runners = {}
        self._sts_fit_params = {}
        self._tts_runners = {}
        self._tts_results = {}
        self._tts_fit_params = {}
        self._exact_qubit_freqs = {}
        self._ro_freqs = {}
        self._dro_results = {}
        self._dr_results = {}
        self._dd_results = {}
        self._dhe_results = {}
        self._resc_results = {}

        self._q_awg_params = None
        self._ro_awg_params = None

        self._ramsey_offset = 5e3
        m = Measurement("", "", devs_aliases_map)
        self._vna = m._vna
        self._exc_iqvg = m._exc_iqvg
        for iqvg in self._exc_iqvg:
            iqvg.set_output_state("OFF")
        self._bias_src = m._bias_src
        self._bias_unit = BiasType.NAMES[self._bias_src[0].get_bias_type()][-2]

        self._launch_date = datetime.today()

    def run(self, qubits_to_measure=[0, 1, 2, 3, 4, 5], period_fraction=0):

        self._logger.debug(
            "Started measurement for qubits ##:" + str(qubits_to_measure))


        ro = ResonatorOracle(self._vna, self._sample_name, self._s_parameter)
        scan_areas = ro.launch()[:]

        for idx, res_limits in enumerate(scan_areas):
            if idx not in qubits_to_measure:
                continue

            qubit_name = self._qubit_names[idx]
            self._res_limits[qubit_name] = res_limits


            STSR = STSRunner(self._sample_name,
                             qubit_name,
                             mean(res_limits),
                             self._res_limits[qubit_name],
                             vna=self._vna,
                             bias_src=self._bias_src)  # {"q_awg": self._q_awg,"ro_awg": self._ro_awg}

            self._sts_runners[qubit_name] = STSR
            self._sts_fit_params[qubit_name], loss = STSR.run()
            self._res_limits[qubit_name] = STSR.get_scan_area()

            TTSR = TTSRunner(self._sample_name,
                             qubit_name,
                             self._res_limits[qubit_name],
                             self._sts_fit_params[qubit_name],
                             vna=self._vna,
                             exc_iqvg=self._exc_iqvg,
                             cur_src=self._bias_src)
            self._tts_runners[qubit_name] = TTSR
            self._tts_fit_params[qubit_name] = TTSR.run()

            period = self._tts_fit_params[qubit_name][0]

            if GlobalParameters().which_sweet_spot[qubit_name] == "top":
                sws_bias = self._tts_fit_params[qubit_name][1]

            elif GlobalParameters().which_sweet_spot[qubit_name] == "bottom":
                sws_bias = self._tts_fit_params[qubit_name][1] - period/2

            ASTSRunner = ACStarkRunner(self._sample_name,
                                       qubit_name,
                                       self._res_limits[qubit_name],
                                       self._tts_fit_params[qubit_name],
                                       vna=self._vna,
                                       exc_iqvg=self._exc_iqvg,
                                       bias_src=self._bias_src)
            q_freq_sws, power = ASTSRunner.launch(sws_bias)

            vna = self._vna[0]
            vna.set_parameters({"freq_limits": self._res_limits[qubit_name],
                                "power": GlobalParameters().readout_power,
                                "averages": 1000,
                                "bandwidth": 1e5,
                                "nop": 201})
            vna.sweep_single()
            freqs, sdata = vna.get_frequencies(), vna.get_sdata()
            try:
                rd = ResonatorDetector(freqs, sdata, True, False,
                                       type=GlobalParameters().resonator_type)
                self._ro_freqs[qubit_name], amp, phase = rd.detect()
            except:
                rd = ResonatorDetector(freqs, sdata, True, True,
                                       type=GlobalParameters().resonator_type)
                self._ro_freqs[qubit_name], amp, phase = rd.detect()

            self._logger.debug(
                "Readout freq is set to %.5e" % self._ro_freqs[qubit_name] +
                f" @ {amp:.2e} {phase:.2e}")

            # period_fraction = float(input("Enter bias offset in period fraction: "))
            for period_fraction in linspace(0, 0.25, 10)[0:1]:
                bias = sws_bias + period_fraction * period
                # q_freq = transmon_spectrum(bias, *self._tts_fit_params[qubit_name][:-1])
                q_freq = q_freq_sws

                pulsed_msg = "Pulsed measurements at %.3f GHz, %.2e %s, " \
                             "%.2e periods away from sws" % (q_freq / 1e9,
                                                             bias,
                                                             self._bias_unit,
                                                             period_fraction)
                self._logger.debug(pulsed_msg)
                self._bias_src[0].set(bias)

                self._exact_qubit_freqs[qubit_name] = q_freq

                # self._perform_readout_excitation_shift_calibration(qubit_name)
                # return
                self._perform_Rabi_oscillations(qubit_name, True)

                self._max_ramsey_delay = .5e3
                self._ramsey_offset = 10e6
                self._ramsey_nop = 201

                self._perform_Ramsey_oscillations(qubit_name)
                detected_ramsey_freq, error = \
                    self._dr_results[qubit_name].get_ramsey_frequency()
                frequency_error = self._ramsey_offset - detected_ramsey_freq
                self._exact_qubit_freqs[qubit_name] -= frequency_error
                self._ramsey_offset = RamseyParameters().detuning
                self._max_ramsey_delay = RamseyParameters().max_ramsey_delay
                self._ramsey_nop = RamseyParameters().nop

                self._perform_Rabi_oscillations(qubit_name, True)
                self._perform_Ramsey_oscillations(qubit_name, True)

                self._perform_hahn_echo(qubit_name, True)

                self._perform_decay(qubit_name, True)

    def _perform_decay(self, qubit_name, save=False):

        DD = DispersiveDecay("%s-decay" % qubit_name,
                             self._sample_name,
                             vna=self._vna,
                             q_awg=[self._exc_iqvg[0].get_iqawg()],
                             ro_awg=[self._vna[0].get_iqawg()],
                             exc_iqvg=self._exc_iqvg)

        readout_delays = linspace(0,
                                  DecayParameters().max_readout_delay,
                                  DecayParameters().nop)
        exc_frequency = self._exact_qubit_freqs[qubit_name]
        pi_pulse_duration = \
            self._dro_results[qubit_name].get_pi_pulse_duration() * 1e3

        pulse_sequence_parameters = {"awg_trigger_reaction_delay": 0,
                                     "readout_duration": DecayParameters().readout_duration,
                                     "repetition_period": DecayParameters().repetition_period,
                                     "pi_pulse_duration": pi_pulse_duration}

        vna_parameters = {"bandwidth": 1 / pulse_sequence_parameters[
            "readout_duration"] * 1e9,
                          "freq_limits": [self._ro_freqs[qubit_name]] * 2,
                          "nop": 1,
                          "averages": DecayParameters().averages,
                          "power": GlobalParameters().readout_power,
                          "adc_trigger_delay": pulse_sequence_parameters[
                                                   "repetition_period"]
                                               - pulse_sequence_parameters[
                                                   "readout_duration"]

                          }

        ro_awg_params = {"calibration":
            self._vna[0].get_calibration(
                self._ro_freqs[qubit_name],
                GlobalParameters().readout_power)}
        q_awg_params = {"calibration":
            self._exc_iqvg[0].get_calibration(
                self._exact_qubit_freqs[qubit_name],
                GlobalParameters().excitation_power)}

        exc_iqvg_parameters = {'power': GlobalParameters().excitation_power,
                               'freq': exc_frequency}

        DD.set_fixed_parameters(pulse_sequence_parameters,
                                vna=[vna_parameters],
                                ro_awg=[ro_awg_params],
                                q_awg=[q_awg_params],
                                exc_iqvg=[exc_iqvg_parameters])
        DD.set_swept_parameters(readout_delays)
        # MeasurementResult.close_figure_by_window_name("Resonator fit")
        dd_result = DD.launch()
        self._dd_results[qubit_name] = dd_result
        if save:
            dd_result.save()

    def _perform_Ramsey_oscillations(self, qubit_name, save=False):

        DR = DispersiveRamsey("%s-ramsey" % qubit_name,
                              self._sample_name,
                              vna=self._vna,
                              q_awg=[self._exc_iqvg[0].get_iqawg()],
                              ro_awg=[self._vna[0].get_iqawg()],
                              exc_iqvg=self._exc_iqvg)

        ramsey_delays = linspace(0, self._max_ramsey_delay, self._ramsey_nop)
        exc_frequency = self._exact_qubit_freqs[
                            qubit_name] - self._ramsey_offset
        pi_pulse_duration = \
            self._dro_results[qubit_name].get_pi_pulse_duration() * 1e3

        pulse_sequence_parameters = {
            "awg_trigger_reaction_delay": 0,
            "readout_duration": RamseyParameters().readout_duration,
            "repetition_period": RamseyParameters().repetition_period,
            "half_pi_pulse_duration": pi_pulse_duration / 2}

        vna_parameters = {
            "bandwidth": 1 / pulse_sequence_parameters[
                "readout_duration"] * 1e9,
            "freq_limits": [self._ro_freqs[qubit_name]] * 2,
            "nop": 1,
            "averages": RamseyParameters().averages,
            "power": GlobalParameters().readout_power,
            "adc_trigger_delay": pulse_sequence_parameters["repetition_period"]
                                 - pulse_sequence_parameters[
                                     "readout_duration"]
        }

        ro_awg_params = {"calibration":
            self._vna[0].get_calibration(
                self._ro_freqs[qubit_name],
                GlobalParameters().readout_power)}
        q_awg_params = {"calibration":
            self._exc_iqvg[0].get_calibration(
                self._exact_qubit_freqs[qubit_name],
                GlobalParameters().excitation_power)}

        exc_iqvg_parameters = {'power': GlobalParameters().excitation_power,
                               'freq': exc_frequency}

        DR.set_fixed_parameters(pulse_sequence_parameters,
                                vna=[vna_parameters],
                                ro_awg=[ro_awg_params],
                                q_awg=[q_awg_params],
                                exc_iqvg=[exc_iqvg_parameters])
        DR.set_swept_parameters(ramsey_delays)
        MeasurementResult.close_figure_by_window_name("Resonator fit")

        dr_result = DR.launch()
        self._dr_results[qubit_name] = dr_result
        if save:
            dr_result.save()

    def _perform_hahn_echo(self, qubit_name, save=False):

        DHE = DispersiveHahnEcho("%s-echo" % qubit_name,
                                 self._sample_name,
                                 vna=self._vna,
                                 q_awg=[self._exc_iqvg[0].get_iqawg()],
                                 ro_awg=[self._vna[0].get_iqawg()],
                                 exc_iqvg=self._exc_iqvg)

        echo_delays = linspace(0,
                               HahnEchoParameters().max_echo_delay,
                               HahnEchoParameters().nop)
        exc_frequency = self._exact_qubit_freqs[qubit_name]
        pi_pulse_duration = \
            self._dro_results[qubit_name].get_pi_pulse_duration() * 1e3

        pulse_sequence_parameters = \
            {"awg_trigger_reaction_delay": 0,
             "readout_duration": HahnEchoParameters().readout_duration,
             "repetition_period": HahnEchoParameters().repetition_period,
             "half_pi_pulse_duration": pi_pulse_duration / 2}

        vna_parameters = {"bandwidth": 1 / pulse_sequence_parameters[
            "readout_duration"] * 1e9,
                          "freq_limits": [self._ro_freqs[qubit_name]] * 2,
                          "nop": 1,
                          "averages": HahnEchoParameters().averages,
                          "power": GlobalParameters().readout_power,
                          "adc_trigger_delay": pulse_sequence_parameters[
                                                   "repetition_period"]
                                               - pulse_sequence_parameters[
                                                   "readout_duration"]
                          }

        ro_awg_params = {"calibration":
            self._vna[0].get_calibration(
                self._ro_freqs[qubit_name],
                GlobalParameters().readout_power)}
        q_awg_params = {"calibration":
            self._exc_iqvg[0].get_calibration(
                self._exact_qubit_freqs[qubit_name],
                GlobalParameters().excitation_power)}

        exc_iqvg_parameters = {'power': GlobalParameters().excitation_power,
                               'freq': exc_frequency}

        DHE.set_fixed_parameters(pulse_sequence_parameters,
                                 vna=[vna_parameters],
                                 ro_awg=[ro_awg_params],
                                 q_awg=[q_awg_params],
                                 exc_iqvg=[exc_iqvg_parameters])
        DHE.set_swept_parameters(echo_delays)
        MeasurementResult.close_figure_by_window_name("Resonator fit")

        dhe_result = DHE.launch()
        self._dhe_results[qubit_name] = dhe_result
        if save:
            dhe_result.save()

    def _perform_Rabi_oscillations(self, qubit_name, save=False):
        DRO = DispersiveRabiOscillations("%s-rabi" % qubit_name,
                                         self._sample_name,
                                         vna=self._vna,
                                         exc_iqvg=self._exc_iqvg,
                                         q_awg=[self._exc_iqvg[0].get_iqawg()],
                                         ro_awg=[self._vna[0].get_iqawg()],
                                         plot_update_interval=0.5)

        exc_frequency = self._exact_qubit_freqs[qubit_name]
        excitation_durations = linspace(0,
                                        RabiParameters().max_excitation_duration,
                                        RabiParameters().nop)

        rabi_sequence_parameters = \
            {"awg_trigger_reaction_delay": 0,
             "excitation_amplitude": 1,
             "readout_duration": RabiParameters().readout_duration,
             "repetition_period": RabiParameters().repetition_period,
             "end_gap": 100,
             "readout_excitation_gap": 10}

        vna_parameters = \
            {"bandwidth": 1 / (rabi_sequence_parameters[
                                   "readout_duration"] +
                               rabi_sequence_parameters["end_gap"]) *
                          1e9,
             "freq_limits": [self._ro_freqs[qubit_name]] * 2,
             "nop": 1,
             "averages": RabiParameters().averages,
             "power": GlobalParameters().readout_power,
             "adc_trigger_delay": rabi_sequence_parameters[
                                      "repetition_period"]
                                  - rabi_sequence_parameters[
                                      "readout_duration"]
                                  - rabi_sequence_parameters[
                                      "end_gap"]
             }

        ro_awg_params = {"calibration":
            self._vna[0].get_calibration(
                self._ro_freqs[qubit_name],
                GlobalParameters().readout_power)}
        q_awg_params = {"calibration":
            self._exc_iqvg[0].get_calibration(
                self._exact_qubit_freqs[qubit_name],
                GlobalParameters().excitation_power)}

        exc_iqvg_parameters = {'power': GlobalParameters().excitation_power,
                               'freq': exc_frequency}

        DRO.set_fixed_parameters(rabi_sequence_parameters,
                                 vna=[vna_parameters],
                                 ro_awg=[ro_awg_params],
                                 q_awg=[q_awg_params],
                                 exc_iqvg=[exc_iqvg_parameters])
        DRO.set_swept_parameters(excitation_durations)
        DRO.set_ult_calib(False)
        # MeasurementResult.close_figure_by_window_name("Resonator fit")

        dro_result = DRO.launch()
        self._dro_results[qubit_name] = dro_result
        if save:
            dro_result.save()

    def _perform_readout_excitation_shift_calibration(self, qubit_name,
                                                      save=False):
        RESC = \
            ReadoutExcitationShiftCalibration("%s-resc" % qubit_name,
                                              self._sample_name,
                                              vna=self._vna,
                                              exc_iqvg=self._exc_iqvg,
                                              q_awg=[self._exc_iqvg[
                                                         0].get_iqawg()],
                                              ro_awg=[
                                                  self._vna[0].get_iqawg()])

        exc_frequencies = linspace(self._exact_qubit_freqs[qubit_name] +
                                   10e6, self._exact_qubit_freqs[
                                       qubit_name] - 100e6, 101)

        readout_excitation_gaps = linspace(100, -3000, 101)

        rabi_sequence_parameters = \
            {"awg_trigger_reaction_delay": 0,
             "excitation_amplitude": 1,
             "readout_duration": 2000,
             "excitation_duration": 300,
             "repetition_period": 20000,
             "end_gap": 4000}

        vna_parameters = \
            {"bandwidth": 1 / (rabi_sequence_parameters[
                                   "readout_duration"] +
                               rabi_sequence_parameters["end_gap"]) *
                          1e9,
             "freq_limits": [self._ro_freqs[qubit_name]] * 2,
             "nop": 1,
             "averages": 30000,
             "power": GlobalParameters().readout_power,
             "adc_trigger_delay": rabi_sequence_parameters[
                                      "repetition_period"]
                                  - rabi_sequence_parameters[
                                      "readout_duration"]
                                  - rabi_sequence_parameters[
                                      "end_gap"]
             }

        exc_iqvg_parameters = {'power': GlobalParameters().excitation_power}

        RESC.set_fixed_parameters(rabi_sequence_parameters,
                                  vna=[vna_parameters],
                                  exc_iqvg=[exc_iqvg_parameters])
        RESC.set_swept_parameters(readout_excitation_gaps, exc_frequencies)
        RESC.set_ult_calib(False)
        # MeasurementResult.close_figure_by_window_name("Resonator fit")

        resc_result = RESC.launch()
        self._resc_results[qubit_name] = resc_result
        if save:
            resc_result.save()
