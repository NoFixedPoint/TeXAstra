"""Distribution discovery, compatibility failures, selection and environment reports."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from cpp_client import Client, ROOT, linux

prefix = ['wsl', '-d', 'Ubuntu-22.04', '--exec'] if os.name == 'nt' else []
backend = linux(ROOT/'native/runtime/texastra-backend')
report = {'checks': []}
project = ROOT/'.work/distribution project'
project.mkdir(parents=True, exist_ok=True)
source = '\\documentclass{article}\n\\begin{document}Selected distribution.\\end{document}\n'
(project/'paper.tex').write_text(source, encoding='utf-8')


def check(name, ok):
    print(name, bool(ok), flush=True)
    report['checks'].append({'name': name, 'ok': bool(ok)})
    assert ok, name


def host(code, *args):
    return subprocess.check_output(prefix+['python3', '-c', code, *args], text=True, encoding='utf-8').strip()


def environment(selected=None, extra=(), settings=None):
    args = prefix+['env']+[key+'='+value for key, value in (settings or {}).items()]
    args += [backend, '--environment']+(['--tex-bin', selected] if selected else [])+list(extra)
    process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=60)
    result = json.loads(process.stdout)
    assert process.returncode == (0 if result['ok'] else 1), process.stderr
    return result


temporary = host('import tempfile; print(tempfile.mkdtemp(prefix="texastra-distribution-"))')
settings = {'XDG_CACHE_HOME': temporary+'/cache'}


def install(name, kpse=None, omit=()):
    directory = temporary+'/'+name
    host('''import pathlib,sys
p=pathlib.Path(sys.argv[1]);p.mkdir()
for name in ['kpsewhich','lualatex','pdflatex','xelatex','bibtex','biber','makeindex']:
 if name not in sys.argv[2:]: (p/name).symlink_to('/usr/bin/'+name)
''', directory, *omit)
    if kpse is not None:
        write(directory+'/kpsewhich', kpse, executable=True)
    return directory


def write(path, data, executable=False):
    host('''import pathlib,sys
p=pathlib.Path(sys.argv[1]);p.unlink(missing_ok=True);p.write_text(sys.argv[2])
if sys.argv[3]=='yes':p.chmod(0o755)
''', path, data, 'yes' if executable else 'no')


try:
    default = environment(settings=settings)
    check('discovers installed kpathsea', default['ok'] and default['binDirectory'] in default['candidates'])
    check('reports engine distribution format and dependencies', all(default.get(k) for k in ['bundledEngine', 'bundledEngineSha256', 'distributionEngine', 'format', 'dependencies', 'texmfRoot', 'texmfcnf']))
    check('initial compatibility compile is cold', not default['preflightReused'])
    repeated = environment(settings=settings)
    check('unchanged preflight reuses verified dependencies', repeated['preflightReused'] and repeated['identity'] == default['identity'])
    check('configuration and filename databases are fingerprinted', any(name.endswith('texmf.cnf') for name in default['lookupFiles']) and default['toolStamps']['kpsewhich'])
    config_dir = temporary+'/config'
    host('import pathlib,sys;pathlib.Path(sys.argv[1]).mkdir()', config_dir)
    write(config_dir+'/texmf.cnf', '% isolated configuration\n')
    overridden_settings = {**settings, 'TEXMFCNF': config_dir+':'+default['texmfcnf']}
    overridden = environment(settings=overridden_settings)
    check('inherited lookup overrides are explicit in report', overridden['ok'] and overridden['lookupOverrides']['TEXMFCNF'] == overridden_settings['TEXMFCNF'])
    check('custom configuration participates in fingerprint', config_dir+'/texmf.cnf' in overridden['lookupFiles'])
    write(config_dir+'/texmf.cnf', '% changed isolated configuration\n')
    changed_config = environment(settings=overridden_settings)
    check('configuration changes invalidate preflight cache', changed_config['ok'] and not changed_config['preflightReused'] and overridden['identity'] != changed_config['identity'])
    selected = install('selected bin')
    chosen = environment(selected, settings=settings)
    check('explicit installation overrides PATH', chosen['ok'] and chosen['binDirectory'] == selected)
    check('all auxiliary tools belong to selected directory', all(chosen['tools'][name] == selected+'/'+name for name in ['bibtex', 'biber', 'makeindex', 'kpsewhich']))
    check('different installation changes cache identity', chosen['identity'] != default['identity'])
    via_path = environment(settings={**settings, 'PATH': selected+':/usr/bin:/bin'})
    check('discovers installation from PATH first', via_path['binDirectory'] == selected)
    for selected_bad in ['relative/bin', temporary+'/absent']:
        failed = environment(selected_bad, settings=settings)
        check('invalid explicit selection is actionable '+selected_bad, not failed['ok'] and ('absolute directory' in failed['error'] or 'kpsewhich' in failed['error']))
    missing = install('missing format', '#!/bin/sh\nfor arg do\n if [ "$arg" = lualatex.fmt ]; then exit 1; fi\ndone\nexec /usr/bin/kpsewhich "$@"\n')
    failed = environment(missing, settings=settings)
    check('missing format explains distribution maintenance', not failed['ok'] and 'lualatex.fmt is missing' in failed['error'])
    comparison = environment(missing, ['--preview-mode', 'full', '--compiler', 'pdflatex'], settings)
    check('full comparison checks its own compiler without Lua format', comparison['ok'] and comparison['mode'] == 'pdflatex')
    broken_fmt = temporary+'/broken.fmt'
    write(broken_fmt, 'This is not a compatible format.\n')
    bad = install('bad format', '#!/bin/sh\nfor arg do\n if [ "$arg" = lualatex.fmt ]; then printf "%s\\n" "'+broken_fmt+'"; exit 0; fi\ndone\nexec /usr/bin/kpsewhich "$@"\n')
    failed = environment(bad, settings=settings)
    check('incompatible format fails actual bundled engine probe', not failed['ok'] and 'compatibility compile' in failed['error'])
    check('compatibility probe leaves selected format untouched', host('import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text().strip())', broken_fmt) == 'This is not a compatible format.')
    # Copy the real format, then replace it without changing the kpse wrapper.
    fmt = temporary+'/selected.fmt'
    host('import shutil,sys;shutil.copyfile(sys.argv[1],sys.argv[2])', default['format'], fmt)
    mutable = install('mutable format', '#!/bin/sh\nfor arg do\n if [ "$arg" = lualatex.fmt ]; then printf "%s\\n" "'+fmt+'"; exit 0; fi\ndone\nexec /usr/bin/kpsewhich "$@"\n')
    first = environment(mutable, settings=settings)
    check('compatible copied format compiles', first['ok'])
    check('copied format cache is reusable', environment(mutable, settings=settings)['preflightReused'])
    write(fmt, 'Changed incompatible format.\n')
    check('format changes invalidate compatibility cache', not environment(mutable, settings=settings)['ok'])
    absent_tool = install('no bibtex', omit=['bibtex'])
    optional = environment(absent_tool, settings=settings)
    check('unused optional tools do not block preflight', optional['ok'] and optional['tools']['bibtex'] is None)
    (project/'refs.bib').write_text('@book{x,author={A Example},title={Selected Tools},year={2020},publisher={Example}}\n')
    citation = '\\documentclass{article}\n\\begin{document}\\cite{x}\\bibliographystyle{plain}\\bibliography{refs}\\end{document}\n'
    with Client(project, main='paper.tex', tex_bin=absent_tool, environment=settings) as client:
        failed = client.request(type='start', overlays={'paper.tex': citation})
        check('required missing tool cannot fall back to PATH', not failed['ok'] and "'bibtex' is missing" in failed['error'] and absent_tool in failed['error'])
    marker = temporary+'/bibtex-used'
    write(selected+'/bibtex', '#!/bin/sh\nprintf used > "'+marker+'"\nexec /usr/bin/bibtex "$@"\n', executable=True)
    # A unique citation fingerprint forces the selected executable to run.
    (project/'refs.bib').write_text((project/'refs.bib').read_text()+'% '+temporary+'\n')
    with Client(project, main='paper.tex', tex_bin=selected, environment=settings) as client:
        result = client.request(type='start', overlays={'paper.tex': citation})
        check('selected tool executes on real bibliography build', result.get('ok') and host('import pathlib,sys;print(pathlib.Path(sys.argv[1]).exists())', marker) == 'True')
        saved = json.loads(host('import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text())', result['environmentReport']))
        check('build report includes actual external dependencies', saved['projectDependencies'] and saved['binDirectory'] == selected)
    missing_source = source.replace('\\begin{document}', '\\usepackage{bakoDeliberatelyMissing}\n\\begin{document}')
    with Client(project, main='paper.tex', tex_bin=selected, environment=settings) as client:
        failed = client.request(type='start', overlays={'paper.tex': missing_source})
        check('missing package names file installation and remedy', not failed['ok'] and 'bakoDeliberatelyMissing.sty' in failed['error'] and selected in failed['error'] and 'package manager' in failed['error'])
    with Client(project, main='paper.tex', tex_bin=selected, environment=settings) as client:
        check('selected project builds', client.request(type='start').get('ok'))
    with Client(project, main='paper.tex', tex_bin=selected, environment=settings) as client:
        check('same distribution reuses project cache', client.request(type='start')['cacheReused'])
    with Client(project, main='paper.tex', tex_bin=default['binDirectory'], environment=settings) as client:
        check('distribution switch invalidates project cache', not client.request(type='start')['cacheReused'])
    slow = install('slow probe', '#!/bin/sh\n/bin/sleep 30\n')
    failed = environment(slow, settings=settings)
    check('hung discovery process is bounded', not failed['ok'] and 'timed out' in failed['error'])
    check('preflight does not modify project sources', (project/'paper.tex').read_text() == source and sorted(p.name for p in project.iterdir()) == ['paper.tex', 'refs.bib'])
finally:
    report['runtimeSha256'] = hashlib.sha256((ROOT/'native/runtime/texastra-backend').read_bytes()).hexdigest()
    (ROOT/'results/distribution.json').write_text(json.dumps(report, indent=2)+'\n')
    host('import pathlib,shutil,sys;p=pathlib.Path(sys.argv[1]);assert p.parent==pathlib.Path("/tmp") and p.name.startswith("texastra-distribution-");shutil.rmtree(p)', temporary)
