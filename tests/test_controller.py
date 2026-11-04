from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from davilex.controller import controller_mode,configuration,select_controller

ROOT=Path(__file__).resolve().parents[1]


class ControllerTests(unittest.TestCase):
    def test_exit_restores_input_and_keeps_unrelated_game_changes(self):
        with tempfile.TemporaryDirectory(prefix='controller-test-',dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'game.ini'
            original=b'[INPUT]\r\nDEVICE=1\r\n[PLAYER]\r\nmoney=100\r\n'
            config.write_bytes(original)
            with patch('davilex.menu.verify_copy',return_value=(directory/'menu.exe',directory/'spel.dat')):
                with controller_mode(directory,'a2ii-timing'):
                    self.assertIn(b'DEVICE=3',config.read_bytes())
                    self.assertTrue((directory/'Xidi.32.dll').exists())
                    config.write_bytes(config.read_bytes().replace(b'money=100',b'money=250'))
            self.assertEqual(config.read_bytes(),original.replace(b'money=100',b'money=250'))
            self.assertFalse((directory/'Xidi.32.dll').exists())
            self.assertFalse((directory/'winmm.dll').exists())

    def test_existing_wrapper_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='controller-test-',dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'game.ini'
            original=b'[INPUT]\nDEVICE=1\n';config.write_bytes(original)
            (directory/'dinput.dll').write_bytes(b'existing wrapper')
            with patch('davilex.menu.verify_copy',return_value=(directory/'menu.exe',directory/'spel.dat')):
                with self.assertRaises(ValueError):
                    with controller_mode(directory,'a2ii-timing'):pass
            self.assertEqual(config.read_bytes(),original)
            self.assertEqual((directory/'dinput.dll').read_bytes(),b'existing wrapper')

    def test_europe_retains_existing_joystick_bindings(self):
        with tempfile.TemporaryDirectory(prefix='controller-test-',dir=ROOT/'work') as folder:
            directory=Path(folder);(directory/'Ini').mkdir()
            config=directory/'Ini/game.ini'
            bindings={'TurnLeft':'JS_RIGHT','TurnRight':'JS_LEFT','MoveForward':'JS_UP',
                      'MoveBack':'JS_DOWN','Turbo':'JS_BUTTON4','HandBrake':'JS_BUTTON3',
                      'Horn':'JS_BUTTON2','Reset':'JS_BUTTON1'}
            original=('[InputGeneral]\nInputDevice=Keyboard\n[InputKeyBinds]\n'+
                      ''.join(f'{key}={value}\n' for key,value in bindings.items())).encode()
            config.write_bytes(original)
            _,changes=configuration(directory/'spel.exe','europe-timing')
            self.assertEqual(changes,{('InputGeneral','InputDevice'):'AnalogController'})
            select_controller(directory/'spel.exe','europe-timing')
            self.assertEqual(config.read_bytes(),original.replace(b'InputDevice=Keyboard',b'InputDevice=AnalogController'))


if __name__=='__main__':unittest.main()
