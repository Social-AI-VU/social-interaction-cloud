"""
build_localvqe.py

Fetch and build LocalVQE's liblocalvqe.so into this package's lib/ dir.
Stdlib-only: loaded by file path from setup.py's build_ext on every source
build, and installed as the `sic-build-localvqe` console script.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request

DEFAULT_REPO_URL = "https://github.com/localai-org/LocalVQE.git"
DEFAULT_SRC_DIR = os.path.join("~", ".cache", "sic", "localvqe-src")
DEFAULT_MODEL_DIR = os.path.join("~", ".cache", "sic", "models")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_LIB_DIR = os.path.join(PACKAGE_DIR, "lib")

# liblocalvqe.so dladdr-locates the libggml-cpu-*.so backend variants at
# runtime, so all shipped libraries must stay co-located.
LIB_PATTERNS = ("liblocalvqe.so*", "libggml*.so*", "liblocalvqe*.dylib", "libggml*.dylib")

DEFAULT_MODEL_NAME = "localvqe-v1.3-4.8M-f32.gguf"

# URLs and SHA-256 checksums as published in LocalVQE's ggml/CMakeLists.txt.
HF_MODEL_BASE = "https://huggingface.co/LocalAI-io/LocalVQE/resolve/main/"
KNOWN_MODELS = {
    "localvqe-v1.3-4.8M-f32.gguf": "c4f7912485c32cfc206c536f2f050b52513f2f613fdbc616391f6b26ab1d51ec",
    "localvqe-v1.2-1.3M-f32.gguf": "4856ecf5f522b23fb2bc5caeac81f323c0ef1c4c156a9c7d40a6adbe092ba9ce",
    "localvqe-v1.4-aec-200K-f32.gguf": "b6e43138588a83bfe903ab5e143b4020b91c1e1629f5a575ac5855ff0003c731",
}
# Doubletalk mic/ref example clips (used by the parity self-test and demos).
KNOWN_TESTDATA = {
    "dt_mic.wav": (
        "https://huggingface.co/spaces/LocalAI-io/LocalVQE-demo/resolve/main/examples/dt_mic.wav",
        "8d0c15e56a4c7f387847451952123e8f23161520e81c1ba8878c922f11592a62",
    ),
    "dt_ref.wav": (
        "https://huggingface.co/spaces/LocalAI-io/LocalVQE-demo/resolve/main/examples/dt_ref.wav",
        "e931d49e2802c1d7b15750caff1455495cd1dc40d27cb2fe51a8c58cbebe60fe",
    ),
}



def _run(cmd, cwd=None):
    print("[sic-localvqe] $ " + " ".join(cmd) + ("" if cwd is None else "  (in {})".format(cwd)))
    sys.stdout.flush()
    subprocess.check_call(cmd, cwd=cwd)


def _is_on_branch(src_dir):
    return (
        subprocess.call(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=src_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        == 0
    )


def ensure_checkout(repo=None, ref=None, src_dir=None):
    """Clone or fetch/pull LocalVQE (with its ggml submodule) into the cache dir."""
    repo = repo or os.environ.get("LOCALVQE_REPO") or DEFAULT_REPO_URL
    ref = ref or os.environ.get("LOCALVQE_REF") or None
    src_dir = os.path.expanduser(src_dir or os.environ.get("LOCALVQE_SRC_DIR") or DEFAULT_SRC_DIR)

    if os.path.isdir(os.path.join(src_dir, ".git")):
        print("[sic-localvqe] reusing existing checkout: {}".format(src_dir))
        _run(["git", "remote", "set-url", "origin", repo], cwd=src_dir)
        _run(["git", "fetch", "--tags", "origin"], cwd=src_dir)
        if ref:
            _run(["git", "checkout", ref], cwd=src_dir)
        if _is_on_branch(src_dir):
            pull = ["git", "pull", "--ff-only", "origin"]
            if ref:
                pull.append(ref)
            _run(pull, cwd=src_dir)
    else:
        parent = os.path.dirname(src_dir)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        # LocalVQE vendors ggml as a git submodule, hence --recursive.
        _run(["git", "clone", "--recursive", repo, src_dir])
        if ref:
            _run(["git", "checkout", ref], cwd=src_dir)

    # --force: cmake patches the vendored ggml tree at configure time, so the
    # submodule is legitimately dirty; reset it and let cmake re-apply.
    _run(["git", "submodule", "update", "--init", "--recursive", "--force"], cwd=src_dir)
    return src_dir


def build_native(src_dir, jobs=None, extra_cmake_args=None):
    """Configure and build the shared library; returns the build directory."""
    ggml_dir = os.path.join(src_dir, "ggml")
    build_dir = os.path.join(ggml_dir, "build")

    configure = [
        "cmake",
        "-S", ggml_dir,
        "-B", build_dir,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DLOCALVQE_BUILD_SHARED=ON",
    ]
    # optional non-system libsndfile so the WAV CLI tools build without root
    sndfile_lib = os.environ.get("SNDFILE_LIBRARY")
    sndfile_inc = os.environ.get("SNDFILE_INCLUDE_DIR")
    if sndfile_lib and sndfile_inc:
        configure.append("-DSNDFILE_LIBRARY={}".format(sndfile_lib))
        configure.append("-DSNDFILE_INCLUDE_DIR={}".format(sndfile_inc))
    env_args = os.environ.get("LOCALVQE_CMAKE_ARGS", "").split()
    configure.extend(env_args)
    if extra_cmake_args:
        configure.extend(extra_cmake_args)

    _run(configure)
    _run(["cmake", "--build", build_dir, "-j", str(jobs or os.cpu_count() or 2)])
    return build_dir


def copy_libs(build_dir, lib_dir=None):
    """Copy liblocalvqe.so + libggml*.so into the package lib/ dir, keeping symlinks."""
    import glob

    bin_dir = os.path.join(build_dir, "bin")
    lib_dir = lib_dir or PACKAGE_LIB_DIR
    if not os.path.isdir(lib_dir):
        os.makedirs(lib_dir)

    sources = []
    for pattern in LIB_PATTERNS:
        sources.extend(glob.glob(os.path.join(bin_dir, pattern)))
    sources = sorted(set(sources))

    if not any(os.path.basename(s).startswith("liblocalvqe.so") for s in sources):
        raise RuntimeError(
            "liblocalvqe.so not found in {} - the build did not produce the "
            "shared library (was -DLOCALVQE_BUILD_SHARED=ON used?)".format(bin_dir)
        )

    # Drop stale copies first so removed CPU variants don't linger.
    for pattern in LIB_PATTERNS:
        for stale in glob.glob(os.path.join(lib_dir, pattern)):
            os.remove(stale)

    installed = []
    for src in sources:
        name = os.path.basename(src)
        dst = os.path.join(lib_dir, name)
        if os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)
        installed.append(name)

    print("[sic-localvqe] installed into {}:".format(lib_dir))
    for name in installed:
        print("[sic-localvqe]   {}".format(name))
    return installed


def missing_build_tools():
    """Return a list of (tool, hint) tuples for required tools that are absent."""
    missing = []
    if not shutil.which("git"):
        missing.append(("git", "needed to clone https://github.com/localai-org/LocalVQE.git"))
    if not shutil.which("cmake"):
        missing.append(("cmake", "cmake >= 3.20 is required"))
    if not (shutil.which("g++") or shutil.which("clang++") or shutil.which("c++")):
        missing.append(("C++ compiler", "a C++17 compiler (g++ or clang++) is required"))
    return missing


def libsndfile_available():
    """Best-effort check for libsndfile development files (optional, CLI-only)."""
    if os.environ.get("SNDFILE_LIBRARY") and os.environ.get("SNDFILE_INCLUDE_DIR"):
        return True
    candidates = ["/usr/include", "/usr/local/include", "/opt/homebrew/include"]
    return any(os.path.isfile(os.path.join(d, "sndfile.h")) for d in candidates)


def build_all(repo=None, ref=None, src_dir=None, lib_dir=None, jobs=None, extra_cmake_args=None):
    """Clone/update, compile, and install the shared libraries. Returns installed names."""
    src = ensure_checkout(repo=repo, ref=ref, src_dir=src_dir)
    build_dir = build_native(src, jobs=jobs, extra_cmake_args=extra_cmake_args)
    return copy_libs(build_dir, lib_dir=lib_dir)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url, dest, sha256=None):
    if os.path.isfile(dest) and sha256 and _sha256(dest) == sha256:
        print("[sic-localvqe] {} already present (checksum OK)".format(dest))
        return dest
    print("[sic-localvqe] downloading {} -> {}".format(url, dest))
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    if sha256:
        got = _sha256(tmp)
        if got != sha256:
            os.remove(tmp)
            raise RuntimeError("checksum mismatch for {}: got {}, expected {}".format(url, got, sha256))
    os.replace(tmp, dest)
    return dest


def download_model(name=DEFAULT_MODEL_NAME, model_dir=None):
    """Download a LocalVQE GGUF from HuggingFace into the model cache dir."""
    model_dir = os.path.expanduser(model_dir or os.environ.get("LOCALVQE_MODEL_DIR") or DEFAULT_MODEL_DIR)
    if not os.path.isdir(model_dir):
        os.makedirs(model_dir)
    sha = KNOWN_MODELS.get(name)
    if sha is None:
        print("[sic-localvqe] warning: no known checksum for {}; skipping verification".format(name))
    return _download(HF_MODEL_BASE + name, os.path.join(model_dir, name), sha256=sha)


def download_testdata(model_dir=None):
    """Download the doubletalk mic/ref example WAV pair next to the models."""
    model_dir = os.path.expanduser(model_dir or os.environ.get("LOCALVQE_MODEL_DIR") or DEFAULT_MODEL_DIR)
    if not os.path.isdir(model_dir):
        os.makedirs(model_dir)
    paths = []
    for name, (url, sha) in sorted(KNOWN_TESTDATA.items()):
        paths.append(_download(url, os.path.join(model_dir, name), sha256=sha))
    return paths


def build_for_setup():
    """
    setup.py build_ext hook: build unconditionally; returns the CMake build
    dir, or None (with printed specifics) when required tools are missing.
    """
    missing = missing_build_tools()
    if missing:
        print("[sic-localvqe] cannot build the LocalVQE native library:")
        for tool, hint in missing:
            print("[sic-localvqe]   - {}: {}".format(tool, hint))
        return None
    if not libsndfile_available():
        print("[sic-localvqe] note: libsndfile not found - optional, only for the WAV CLI tools.")
    src = ensure_checkout()
    build_dir = build_native(src)
    copy_libs(build_dir)
    return build_dir


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="sic-build-localvqe",
        description="Clone and build LocalVQE's liblocalvqe.so for the SIC LocalVQE service "
                    "(same steps as the install-time build_ext hook).",
    )
    parser.add_argument("--repo", default=None, help="git URL (default: $LOCALVQE_REPO or upstream)")
    parser.add_argument("--ref", default=None, help="branch/tag/commit (default: $LOCALVQE_REF or repo default)")
    parser.add_argument("--src-dir", default=None, help="checkout cache dir (default: $LOCALVQE_SRC_DIR or ~/.cache/sic/localvqe-src)")
    parser.add_argument("--lib-dir", default=None, help="destination for the built .so files (default: the packaged lib/ dir)")
    parser.add_argument("--jobs", "-j", type=int, default=None, help="parallel build jobs (default: nproc)")
    parser.add_argument("--cmake-arg", action="append", default=[], metavar="ARG",
                        help="extra cmake configure argument (repeatable)")
    parser.add_argument("--skip-build", action="store_true", help="skip clone+build (e.g. only download assets)")
    parser.add_argument("--download-model", nargs="?", const=DEFAULT_MODEL_NAME, default=None, metavar="GGUF",
                        help="also download a GGUF model (default: {})".format(DEFAULT_MODEL_NAME))
    parser.add_argument("--download-testdata", action="store_true",
                        help="also download the doubletalk mic/ref example WAV pair")
    parser.add_argument("--model-dir", default=None,
                        help="where to store models/testdata (default: $LOCALVQE_MODEL_DIR or ~/.cache/sic/models)")
    args = parser.parse_args(argv)

    if not args.skip_build:
        missing = missing_build_tools()
        if missing:
            for tool, hint in missing:
                print("[sic-localvqe] missing {}: {}".format(tool, hint))
            return 1
        if not libsndfile_available():
            print("[sic-localvqe] note: libsndfile headers not found; WAV CLI tools will be skipped "
                  "(liblocalvqe.so itself does not need libsndfile).")
        build_all(repo=args.repo, ref=args.ref, src_dir=args.src_dir,
                  lib_dir=args.lib_dir, jobs=args.jobs, extra_cmake_args=args.cmake_arg)

    if args.download_model:
        print("[sic-localvqe] model: {}".format(download_model(args.download_model, model_dir=args.model_dir)))
    if args.download_testdata:
        for p in download_testdata(model_dir=args.model_dir):
            print("[sic-localvqe] testdata: {}".format(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
