import unittest
from davilex.quickrace import update_ini


class IniTests(unittest.TestCase):
    def test_only_requested_key_changes_and_comments_survive(self):
        data=b'; engine=1,2;3\r\n[PLAYER]\r\n  CAR = 1\t\r\ncar_model=2\r\n[OTHER]\r\nCAR=5\r\n'
        result=update_ini(data,{('player','car'):6})
        self.assertEqual(result,b'; engine=1,2;3\r\n[PLAYER]\r\n  CAR = 6\t\r\ncar_model=2\r\n[OTHER]\r\nCAR=5\r\n')

    def test_ambiguous_key_is_rejected(self):
        with self.assertRaises(ValueError):
            update_ini(b'[PLAYER]\ncar=0\ncar=1\n',{('PLAYER','car'):2})

    def test_missing_key_is_rejected(self):
        with self.assertRaises(ValueError):
            update_ini(b'[PLAYER]\ncar=0\n',{('PLAYER','damage'):0})

    def test_no_final_newline_is_preserved(self):
        self.assertEqual(update_ini(b'[PLAYER]\ncar=1',{('PLAYER','car'):2}),b'[PLAYER]\ncar=2')
