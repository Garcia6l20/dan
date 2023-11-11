from dan import generator

@generator('assert-error.txt')
def assert_error(self):
    assert False == True, 'realy ?'
