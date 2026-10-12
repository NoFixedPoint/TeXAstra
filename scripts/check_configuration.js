const assert=require('assert');
const {configuration}=require('../extension/configuration');
const scopes=['globalValue','workspaceValue','workspaceFolderValue',
  'globalLanguageValue','workspaceLanguageValue','workspaceFolderLanguageValue'];
let current={},legacy={},value='wsl',checks=0;
const workspace={getConfiguration:(section,resource)=>{
  assert.equal(resource,'project');
  return section==='texastra'?{inspect:()=>current,get:()=>value}:{inspect:()=>legacy};
}};
const read=()=>configuration(workspace,'project').get('runtimeMode','wsl');
assert.equal(read(),'wsl');checks++;
for(const scope of scopes){
  current={};legacy={[scope]:'native'};assert.equal(read(),'native');checks++;
  current={[scope]:'wsl'};assert.equal(read(),'wsl');checks++;
}
current={};legacy={globalValue:'global',workspaceValue:'workspace',workspaceFolderValue:'folder'};
assert.equal(read(),'folder');checks++;
current={workspaceValue:''};value='';assert.equal(read(),'');checks++;
console.log({checks,ok:true});
