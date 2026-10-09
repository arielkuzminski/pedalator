"""Phone mode needs HTTPS (Web Bluetooth only works on secure pages). Pedalator makes its own certificate authority,
which you install once on the phone, and a server certificate for this PC's address."""
from __future__ import annotations

import datetime
import ipaddress
import secrets
import socket
from pathlib import Path

from .state import log


def lan_ip() -> str:
    """This PC's address on the local network (the interface of the default route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # no packet is sent; it only picks the interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def load_token(cert_dir: Path) -> str:
    """The secret in the phone's URL. Created once and kept, so the URL is the same after every restart."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    f = cert_dir / "token.txt"
    token = f.read_text().strip() if f.exists() else ""
    if not token:
        token = secrets.token_urlsafe(8)
        f.write_text(token)
    return token


def ensure_certs(cert_dir: Path, ip: str) -> tuple[Path, Path]:
    """Create (once) the CA and a server certificate valid for ``ip`` and localhost.

    Returns (server certificate, server key). ``ca.crt`` (DER) is what the phone installs.
    Written to be accepted by iOS: ECDSA P-256, SAN with the IP, serverAuth, one year.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    cert_dir.mkdir(parents=True, exist_ok=True)
    pem = serialization.Encoding.PEM
    nokey = serialization.NoEncryption()
    now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)

    ca_crt, ca_key = cert_dir / "ca.pem", cert_dir / "ca.key"
    if ca_crt.exists() and ca_key.exists():
        ca_cert = x509.load_pem_x509_certificate(ca_crt.read_bytes())
        ca_k = serialization.load_pem_private_key(ca_key.read_bytes(), None)
    else:
        ca_k = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Pedalator local CA")])
        ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_k.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now)
                   .not_valid_after(now + datetime.timedelta(days=3650))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                   .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_k.public_key()), critical=False)
                   .sign(ca_k, hashes.SHA256()))
        ca_crt.write_bytes(ca_cert.public_bytes(pem))
        ca_key.write_bytes(ca_k.private_bytes(pem, serialization.PrivateFormat.PKCS8, nokey))
        log(f"created a local certificate authority in {cert_dir} (install ca.crt on the phone once)")
    (cert_dir / "ca.crt").write_bytes(ca_cert.public_bytes(serialization.Encoding.DER))

    srv_crt, srv_key, srv_ip = cert_dir / "server.pem", cert_dir / "server.key", cert_dir / "server.ip"
    if not (srv_crt.exists() and srv_key.exists() and srv_ip.exists() and srv_ip.read_text() == ip):
        k = ec.generate_private_key(ec.SECP256R1())
        san = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        if ip != "127.0.0.1":
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)]))
                .issuer_name(ca_cert.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365))
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.KeyUsage(True, False, False, False, True, False, False, False, False), critical=True)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_k.public_key()), critical=False)
                .sign(ca_k, hashes.SHA256()))
        srv_crt.write_bytes(cert.public_bytes(pem))
        srv_key.write_bytes(k.private_bytes(pem, serialization.PrivateFormat.PKCS8, nokey))
        srv_ip.write_text(ip)
        log(f"server certificate for {ip} created")
    return srv_crt, srv_key
