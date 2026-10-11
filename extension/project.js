const fs=require('fs');
const path=require('path');

function contains(project,file){
  const relative=path.relative(project,file);
  return relative!==''&&!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative);
}

// Keep root discovery independent of VS Code so multi-root and magic comments
// can be checked without starting an extension host.
function resolveMain({configured='',workspace,active,read=file=>fs.readFileSync(file,'utf8')}){
  if(configured){
    if(!path.isAbsolute(configured)&&!workspace)throw new Error('Open a folder or configure an absolute main-file path.');
    const file=path.resolve(workspace||'.',configured);
    if(!fs.existsSync(file))throw new Error(`Root document does not exist: ${file}`);
    return file;
  }
  if(active&&/\.tex$/i.test(active)){
    const source=read(active);
    const magic=source.match(/^\s*%\s*!\s*TEX\s+root\s*=\s*(.+?)\s*$/im);
    if(magic){
      const file=path.resolve(path.dirname(active),magic[1].replace(/^['"]|['"]$/g,''));
      if(!fs.existsSync(file))throw new Error(`The % !TEX root file does not exist: ${file}`);
      return file;
    }
    if(/^\s*\\documentclass(?:\[.*?\])?\s*\{/m.test(source))return active;
  }
  if(workspace){
    for(const relative of ['main.tex','corpus/main.tex']){
      const file=path.join(workspace,relative);
      if(fs.existsSync(file))return file;
    }
  }
  return null;
}

function resolveCompiler(configured,source){
  if(configured&&configured!=='auto')return configured;
  return source.match(/^\s*%\s*!\s*TEX\s+(?:program|TS-program)\s*=\s*(lualatex|xelatex|pdflatex)\s*$/im)?.[1].toLowerCase()||'lualatex';
}
module.exports={contains,resolveMain,resolveCompiler};
