import ctypes

class Capsule:
    def __init__(self, path_to_lib):
        self._path_to_lib = path_to_lib
        self._lib = ctypes.CDLL(self._path_to_lib)
        self._lib.clCCapsule_SetSingleThreaded.argtypes = [ctypes.c_bool]
        self._lib.clCCapsule_SetSingleThreaded(True)
        self._lib.clCCapsule_GetVersionString.restype = ctypes.c_char_p

    def get_path(self):
        return self._path_to_lib
    
    def get_version(self):
        return self._lib.clCCapsule_GetVersionString().decode('utf-8')
    
    def get_lib(self):
        return self._lib