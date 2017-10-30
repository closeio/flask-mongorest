import logging
import struct
import sys
import time

from flask import current_app

from Crypto.Cipher import Blowfish

from zbase62 import zbase62

from flask_mongorest.cursors_pb2 import SequentialCursor
from flask_mongorest.exceptions import ValidationError

INT_SIZE = struct.calcsize('I')

logger = logging.getLogger()

def decode_sequential_cursor(encrypted_data):
    """Decode a sequential cursor into a protocol buffer instance."""

    # Blowfish is fast and cryptographically sufficient for this use
    cipher = Blowfish.BlowfishCipher(current_app.config.get('CURSOR_PASSWORD', 'xyz123'))

    try:
        data = zbase62.a2b(str(encrypted_data))
        decrypted_data = cipher.decrypt(data)

        # Get size of protobuf data
        size = struct.unpack('I', decrypted_data[:INT_SIZE])[0]

        sc = SequentialCursor()
        # Deserialize data into protobuf instance
        sc.ParseFromString(decrypted_data[INT_SIZE:size+INT_SIZE])
    except Exception as e:
        logger.exception('Error decoding cursor')
        raise ValidationError({'error': '_cursor invalid.'})

    return sc

def generate_sequential_cursor(skip, limit):
    """
    Create a sequential cursor.

    A Sequential Cursor stores the skip, limit, and time of creation in an
    encrypted data structure. Protocol buffers are used to serialize the data.
    Protobufs provide very fast serialization and allows easy addition to the
    data fields stored in the cursor.  For instance, we may want to include the
    hash of the query string in the future to provide further validation of the
    cursor.

    Blowfish encryption protects the data and then it is base62 encoded so that
    it is safe to use in URLs.
    """

    # Blowfish is fast and cryptographically sufficient for this use
    cipher = Blowfish.BlowfishCipher(current_app.config.get('CURSOR_PASSWORD', 'xyz123'))

    # Create protobuf instance
    fk = SequentialCursor()
    fk.skip = skip + limit
    fk.limit = limit
    fk.time = int(time.time())

    # Serialize to binary string
    data= fk.SerializeToString()

    # Serial size into 4 byte binary string
    size = len(data)
    size_serialized = struct.pack("I", int(size))

    # Calculate padding to make entire cursor size a multiple of 8 which is
    # required for the BlowFish encryption
    padding = 8 - (size + INT_SIZE) % 8
    data = size_serialized + data
    if padding > 0:
        data = data.ljust(len(data) + padding)

    encrypted_data = cipher.encrypt(data)
    encrypted_data = zbase62.b2a(encrypted_data)
    return encrypted_data
