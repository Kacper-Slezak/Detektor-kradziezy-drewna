"""Versioned SD capture container shared by the LoPy recorder and PC reader."""

try:
    import ustruct as struct
except ImportError:
    import struct

try:
    import ujson as json
except ImportError:
    import json

MAGIC = b'LOPYADC1'
RECORD = '<IIIIIIII'
RECORD_BYTES = struct.calcsize(RECORD)
END = 0xffffffff
MAX_HEADER_BYTES = 4096
VALID = 1
SATURATED_TIMING = 2


def write_exact(stream, data, size):
    if stream.write(data) != size:
        raise OSError('Incomplete SD write')


class CaptureWriter:
    def __init__(self, stream, metadata):
        self.stream = stream
        self.buffer = bytearray(RECORD_BYTES)
        header = json.dumps(metadata).encode('utf-8')
        if len(header) > MAX_HEADER_BYTES:
            raise ValueError('Capture header exceeds size limit')
        write_exact(stream, MAGIC, len(MAGIC))
        write_exact(stream, struct.pack('<I', len(header)), 4)
        write_exact(stream, header, len(header))

    def slot(self, index, delta, delay, skipped, late, rails, flags, capture_us, pcm, timing):
        struct.pack_into(RECORD, self.buffer, 0, index, delta, delay, skipped,
                         late, rails, flags, capture_us)
        write_exact(self.stream, self.buffer, RECORD_BYTES)
        write_exact(self.stream, pcm, 2 * len(pcm))
        write_exact(self.stream, timing, 2 * len(timing))

    def finish(self, count):
        struct.pack_into(RECORD, self.buffer, 0, END, count, 0, 0, 0, 0, 0, 0)
        write_exact(self.stream, self.buffer, RECORD_BYTES)
        self.stream.flush()
