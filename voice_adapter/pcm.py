"""Streaming mono signed-16 little-endian PCM sample-rate conversion."""

import struct


class PcmFormatError(ValueError):
    pass


class LinearPcmResampler:
    """Stateful linear interpolator preserving phase across input chunks.

    Input and output are mono s16le. A small amount of look-ahead is retained
    between chunks. This is intentionally a compact compatibility resampler;
    production voice-quality acceptance still requires listening tests.
    """

    def __init__(self, source_rate, target_rate):
        if (isinstance(source_rate, bool) or not isinstance(source_rate, int)
                or isinstance(target_rate, bool) or not isinstance(target_rate, int)
                or source_rate <= 0 or target_rate <= 0):
            raise PcmFormatError("invalid_sample_rate")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._pending_byte = b""
        self._samples = []
        self._base_index = 0
        self._total_input = 0
        self._next_output = 0
        self._finished = False

    def feed(self, chunk):
        if self._finished:
            raise PcmFormatError("resampler_finished")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise PcmFormatError("invalid_audio_chunk")
        data = self._pending_byte + bytes(chunk)
        usable = len(data) - (len(data) % 2)
        self._pending_byte = data[usable:]
        if usable:
            incoming = struct.unpack("<" + "h" * (usable // 2), data[:usable])
            self._samples.extend(incoming)
            self._total_input += len(incoming)
        return self._emit_ready(final=False)

    def finish(self):
        if self._finished:
            raise PcmFormatError("resampler_finished")
        self._finished = True
        if self._pending_byte:
            raise PcmFormatError("odd_pcm_byte_count")
        return self._emit_ready(final=True)

    def _emit_ready(self, final):
        if not self._total_input:
            return b""
        if final:
            target_count = max(1, (self._total_input * self.target_rate + self.source_rate // 2)
                               // self.source_rate)
        else:
            target_count = None

        result = bytearray()
        while target_count is None or self._next_output < target_count:
            numerator = self._next_output * self.source_rate
            left_global, remainder = divmod(numerator, self.target_rate)
            right_global = left_global + (1 if remainder else 0)
            if final:
                left_global = min(left_global, self._total_input - 1)
                right_global = min(right_global, self._total_input - 1)
            elif right_global >= self._total_input:
                break

            left_index = left_global - self._base_index
            right_index = right_global - self._base_index
            if left_index < 0 or right_index >= len(self._samples):
                raise PcmFormatError("resampler_state_invalid")
            left = self._samples[left_index]
            right = self._samples[right_index]
            value = left + (right - left) * remainder / self.target_rate
            sample = max(-32768, min(32767, int(round(value))))
            result.extend(struct.pack("<h", sample))
            self._next_output += 1

        if not final:
            next_left = (self._next_output * self.source_rate) // self.target_rate
            discard = max(0, min(next_left - self._base_index, len(self._samples) - 1))
            if discard:
                del self._samples[:discard]
                self._base_index += discard
        return bytes(result)
