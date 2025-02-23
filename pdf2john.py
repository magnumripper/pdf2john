#!/usr/bin/env python

import logging
import os
import sys

from pyhanko.pdf_utils.reader import PdfFileReader

logger = logging.getLogger(__name__)


class SecurityRevision:
    """Represents Standard Security Handler Revisions
    and the corresponding key length for the /O and /U entries

    In Revision 5, the /O and /U entries were extended to 48 bytes,
    with three logical parts -- a 32 byte verification hash,
    an 8 byte validation salt, and an 8 byte key salt."""

    revisions = {
        2: 32,  # RC4_BASIC
        3: 32,  # RC4_EXTENDED
        4: 32,  # RC4_OR_AES128
        5: 48,  # AES_R5_256
        6: 48,  # AES_256
    }

    @classmethod
    def get_key_length(cls, revision):
        """
        Get the key length for a given revision,
        defaults to 48 if no revision is specified.
        """
        return cls.revisions.get(revision, 48)


class PdfHashExtractor:
    """
    Extracts hash and encryption information from a PDF file
    """

    def __init__(self, file_name):
        self.file_name = file_name

        with open(file_name, "rb") as doc:
            self.pdf = PdfFileReader(doc, strict=False)
            encrypt_dict = self.pdf._get_encryption_params()

            if not encrypt_dict:
                raise RuntimeError("File not encrypted")

            self.algorithm: int = encrypt_dict.get("/V")
            self.length: int = encrypt_dict.get("/Length", 40)
            self.permissions: int = encrypt_dict["/P"]
            self.revision: int = encrypt_dict["/R"]

    @property
    def document_id(self) -> bytes:
        return self.pdf.document_id[0]

    @property
    def encrypt_metadata(self) -> str:
        """
        Get a string representation of whether metadata is encrypted.

        Returns "1" if metadata is encrypted, "0" otherwise.
        """
        return str(int(self.pdf.security_handler.encrypt_metadata))

    def parse(self) -> str:
        """
        Parse PDF encryption information into a formatted string for John
        """
        passwords = self.get_passwords()
        fields = [
            f"$pdf${self.algorithm}",
            self.revision,
            self.length,
            self.permissions,
            self.encrypt_metadata,
            len(self.document_id),
            self.document_id.hex(),
            passwords,
        ]
        return "*".join(map(str, fields))

    def get_passwords(self) -> str:
        """
        Creates a string consisting of the hexidecimal string of the
        /U, /O, /UE and /OE entries and their corresponding byte string length
        """
        passwords = []
        keys = ("udata", "odata", "oeseed", "ueseed")
        max_key_length = SecurityRevision.get_key_length(self.revision)

        for key in keys:
            if data := getattr(self.pdf.security_handler, key):
                data: bytes = data[:max_key_length]
                passwords.extend([str(len(data)), data.hex()])

        return "*".join(passwords)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: %s <PDF file(s)>", os.path.basename(__file__))
        sys.exit(-1)

    for filename in sys.argv[1:]:
        extractor = PdfHashExtractor(filename)

        try:
            pdf_hash = extractor.parse()
            print(pdf_hash)
        except RuntimeError as error:
            logger.error("%s : %s", filename, error)
