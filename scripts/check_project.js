/* Project discovery checks use temporary fixtures, never user projects. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {resolveMain,resolveCompiler,contains}=require('../extension/project');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'bakoma-project-'));
const root=path.join(directory,'paper with spaces.tex'),chapter=path.join(directory,'chapter.tex');
fs.writeFileSync(root,'\\documentclass{article}\n');
fs.writeFileSync(chapter,'% !TEX root = paper with spaces.tex\nHello');
let checks=0;
function check(actual,expected){assert.deepEqual(actual,expected);checks++;}
check(resolveMain({active:root}),root);
check(resolveMain({active:chapter}),root);
check(resolveMain({configured:'paper with spaces.tex',workspace:directory}),root);
check(resolveMain({configured:root}),root);
check(resolveMain({workspace:directory}),null);
fs.writeFileSync(path.join(directory,'main.tex'),'');
check(resolveMain({workspace:directory}),path.join(directory,'main.tex'));
check(resolveMain({active:root,workspace:directory}),root);
check(resolveCompiler('auto','% !TEX program = XeLaTeX'),'xelatex');
check(resolveCompiler('xelatex','% !TEX program = pdflatex'),'xelatex');
check(resolveCompiler('auto',''),'lualatex');
check(contains(directory,root),true);
check(contains(directory,path.join(directory,'../outside.tex')),false);
check(contains(directory,path.join(directory,'..legitimate.tex')),true);
assert.throws(()=>resolveMain({configured:'missing.tex',workspace:directory}),/does not exist/);checks++;
fs.writeFileSync(chapter,'% !TEX root = missing.tex');
assert.throws(()=>resolveMain({active:chapter}),/does not exist/);checks++;
console.log(JSON.stringify({checks,passed:true}));
