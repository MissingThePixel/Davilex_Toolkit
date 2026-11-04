"""Optional FFmpeg conversion; never goes through Windows file associations."""
from pathlib import Path
import shutil
import subprocess
from .rcs import ArchiveError
from .paths import ROOT
from .process import external_run


def pcm_wav(source, target, *, allow_external=True):
    try:import miniaudio
    except ImportError:miniaudio=None
    if miniaudio is not None:
        try:
            info=miniaudio.get_file_info(str(source))
            decoded=miniaudio.decode_file(str(source),nchannels=info.nchannels,sample_rate=info.sample_rate)
            import wave
            with Path(target).open('xb') as stream:
                with wave.open(stream,'wb') as output:
                    output.setparams((decoded.nchannels,2,decoded.sample_rate,0,'NONE','not compressed'))
                    output.writeframes(decoded.samples.tobytes())
            return Path(target)
        except miniaudio.MiniaudioError:pass
    if not allow_external:raise ArchiveError('Built-in audio decoder could not read this file.')
    bundled=ROOT/'tools/ffmpeg/ffmpeg.exe'
    ffmpeg = str(bundled) if bundled.is_file() else shutil.which('ffmpeg')
    if not ffmpeg:
        raise ArchiveError('FFmpeg is needed for this conversion. Original audio export still works.')
    result = external_run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-i', str(source),
                             '-vn', '-c:a', 'pcm_s16le', str(target)], capture_output=True,
                            timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ArchiveError(result.stderr.decode('utf-8', 'replace')[-1500:])
    return Path(target)
