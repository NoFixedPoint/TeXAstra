const legacySection='bakoma';
const scopes=['workspaceFolderLanguageValue','workspaceLanguageValue','globalLanguageValue',
  'workspaceFolderValue','workspaceValue','globalValue'];
function configuration(workspace,resource){
  const current=workspace.getConfiguration('texastra',resource);
  const legacy=workspace.getConfiguration(legacySection,resource);
  return {get(name,fallback){
    if(!current.inspect)return current.get(name,fallback);
    const configured=current.inspect(name);
    if(scopes.some(scope=>configured?.[scope]!==undefined))return current.get(name,fallback);
    const previous=legacy.inspect(name);
    for(const scope of scopes)if(previous?.[scope]!==undefined)return previous[scope];
    return current.get(name,fallback);
  }};
}
module.exports={configuration};
