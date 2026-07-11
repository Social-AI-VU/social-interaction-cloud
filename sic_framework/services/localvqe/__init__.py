"""
LocalVQE service package: SIC wrapper around LocalVQE's GGML streaming
voice quality enhancement (AEC + noise suppression + dereverb).

Kept import-light: the native binding is only loaded when the service (or
sic_framework.services.localvqe.localvqe_binding) is actually used, so the
sic-build-localvqe entry point works before liblocalvqe.so exists.
"""
