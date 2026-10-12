const fs=require('fs');
const path=require('path');

function contains(project,file){
  const relative=path.relative(project,file);
  return relative!==''&&!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative);
}

function resolveProject({main,workspace,configured=''}){
  const project=configured ? path.resolve(workspace||path.dirname(main),configured)
    : workspace&&contains(workspace,main) ? workspace : path.dirname(main);
  if(!contains(project,main))throw new Error('The main LaTeX file must be inside texastra.projectRoot.');
  if(!fs.statSync(project).isDirectory())throw new Error('The LaTeX project root must be a directory.');
  return project;
}

function supportedFile(project,file){
  if(!contains(project,file))return false;
  const parts=path.relative(project,file).split(path.sep);
  if(parts.some(part=>part.startsWith('.')||part==='node_modules'))return false;
  return /\.(tex|sty|cls|bib|bst|bbl|png|jpg|jpeg|pdf|eps|ps|otf|ttf|tfm|map|enc|cfg|def|clo|fd|ldf|bbx|cbx|lbx|ist|csv|dat|txt|lua)$/i.test(file);
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

function resolveCompiler(configured,source,log=''){
  if(configured&&configured!=='auto')return configured;
  const magic=source.match(/^\s*%\s*!\s*TEX\s+(?:program|TS-program)\s*=\s*(lualatex|xelatex|pdflatex)\s*$/im)?.[1].toLowerCase();
  if(magic)return magic;
  // The saved log is a compiler hint, never an input to the preview build.
  const engine=/^This is (pdfTeX|XeTeX|Lua(?:HB)?TeX)\b/.exec(log)?.[1];
  return ({pdfTeX:'pdflatex',XeTeX:'xelatex',LuaTeX:'lualatex',LuaHBTeX:'lualatex'})[engine]||'lualatex';
}
module.exports={contains,resolveMain,resolveCompiler,resolveProject,supportedFile};
