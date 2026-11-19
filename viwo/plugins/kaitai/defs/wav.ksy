meta:
  id: wav
  title: WAV audio (RIFF)
  file-extension: wav
  endian: le
seq:
  - id: riff_magic
    contents: "RIFF"
  - id: file_size
    type: u4
  - id: wave_magic
    contents: "WAVE"
  - id: format
    type: format_chunk
  - id: chunks
    type: chunk
    repeat: eos
types:
  format_chunk:
    seq:
      - id: chunk_id
        contents: "fmt "
      - id: len
        type: u4
      - id: format_tag
        type: u2
        enum: w_format_tag
      - id: channels
        type: u2
      - id: sample_rate
        type: u4
      - id: byte_rate
        type: u4
      - id: block_align
        type: u2
      - id: bits_per_sample
        type: u2
      - id: rest
        size: len - 16
  chunk:
    seq:
      - id: chunk_id
        size: 4
      - id: len
        type: u4
      - id: data
        size: len
enums:
  w_format_tag:
    1: pcm
    3: ieee_float
    6: alaw
    7: mulaw
    17: adpcm_ima
