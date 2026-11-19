"""Block-compressed textures (doc 18.3), first-party, pure Python, shared by the core's DDS way
back (decode.image) and the plugins that read block data (Godot's VRAM textures): encoders
for BC1 to BC5 (encode_bc.py), BC6H and BC7 (encode_bptc.py), decoders for BC1 to BC5
(decode_bc.py) and BC7 (decode_bc7.py). Below core and beside the plugins (doc 17 layer rule),
so both can import it."""
