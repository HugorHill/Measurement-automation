import os
import sys

sys.path.append('C:\Program Files (x86)\Keysight\SD1\Libraries\Python')
import keysightSD1 as SD1

sys.path.append(os.path.abspath('..\\..\\src\\Python\\'))
from ktqetexperiment_unittests import *
from randomized_benchmarking import *
from ktqet_exceptions import *

AWG_MODEL = 'M3202A'
DIG_MODEL = 'M3102A'


class RandomizedBenchmarkingTestCase(KtQetExperimentTestCase):

    def setUp(self):
        # Call the base setUp function which will create the qubit object
        super(self.__class__, self).setUp()

        # Create the experiment object
        self.experiment = RandomizedBenchmarking(self.qubit)

    def tearDown(self):
        self.experiment.dispose()
        self.experiment = None
        super(self.__class__, self).tearDown()

    def test_constructor(self):
        self.assertNotEqual(self.experiment, None)

    def test_run(self):
        """
        This is the bread and butter function of the experiment.  We will want to go through and test all the validation
        logic, and make sure that the experiment can run, even with simulated hardware.
        :return:
        """

        # The client is required to call all of the appropriate configure functions prior to calling run.
        try:
            self.experiment.run('')
            self.fail()
        except ExperimentNotConfiguredException as e:
            self.assertEqual(str(e), 'Acquisition parameters not configured.')

        # Configure the acquisition
        acquisition_delay = 490
        acquisition_length = 180
        self.experiment.configure_acquisition(acquisition_delay, acquisition_length)

        # Try again, but this time we expect readout parameter exception
        try:
            self.experiment.run('')
            self.fail()
        except ExperimentNotConfiguredException as e:
            self.assertEqual(str(e), 'Readout parameters not configured.')

        # Configure readout
        readout_delay = 50
        ro_wave_i = SD1.SD_Wave()
        ro_wave_i.newFromFile(os.path.abspath('..\\..\\include\\waveforms\\') + '\\' + 'ROwave.csv')
        ro_wave_q = SD1.SD_Wave()
        ro_wave_q.newFromFile(os.path.abspath('..\\..\\include\\waveforms\\') + '\\' + 'ROwave.csv')
        self.experiment.configure_readout(readout_delay, ro_wave_i, ro_wave_q)

        # Try again, but this time we expect pi waveform exception
        try:
            self.experiment.run('')
            self.fail()
        except ExperimentNotConfiguredException as e:
            self.assertEqual(str(e), 'Randomized Benchmarking parameters not configured.')

        Ng = 1
        Nl = 1
        Np = 1 
        Ne = 1
        experiment_delay = 0
        self.experiment.configure_rb_parameters(Ng, Nl, Np, Ne, experiment_delay)
        

        # At this point, the experiment is properly configured however we can expect an exception from an invalid
        # HVI file.
        try:
            self.experiment.run('FakeFile.HVI')
            self.fail()
        except HviException as e:
            self.assertEqual(str(e), 'Failed to open HVI file: FakeFile.HVI.  File does not exist.')

        # Grab the appropriate HVI file
        file_name = 'RB.HVI'
        hvi_folder_path = os.path.abspath('..\\..\\include\\hvi\\')
        file_path = hvi_folder_path + '\\' + file_name

        # This should run (assuming the base class is pointing to appropriate hardware...)
        self.experiment.run(file_path)

        Ng = 100
        Nl = 5
        Np = 5 
        Ne = 20
        experiment_delay = 0
        self.experiment.configure_rb_parameters(Ng, Nl, Np, Ne, experiment_delay)
        self.experiment.run(file_path)



def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(KtQetExperimentTestCase)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(RandomizedBenchmarkingTestCase))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite())
