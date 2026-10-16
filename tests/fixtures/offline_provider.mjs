// Test-only local provider. No HTTP request or account access.
export default function offlineProvider(pi) {
  pi.registerCommand('tte-confirm', {
    description: '离线自动验收：等待状态，脚本会自行关闭',
    handler: async (_args, ctx) => {
      await ctx.ui.confirm('自动验收 · 无需操作', '正在验证状态桥；脚本会自动关闭。');
    },
  });
  pi.registerProvider('tte-offline', {
    name: 'TTE offline test', api: 'tte-offline-api', apiKey: 'offline-test',
    baseUrl: 'http://127.0.0.1',
    models: [{id:'test',name:'Offline test',input:['text'],
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:100000,maxTokens:1024}],
    streamSimple(model) {
      const output={role:'assistant',content:[{type:'text',text:'OFFLINE_TEST_COMPLETE'}],
        api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),stopReason:'stop',
        usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const ready=new Promise(resolve=>setTimeout(resolve,2000));
      let sent=false;
      return {push(){},end(){},result:async()=>{await ready;return output;},
        async *[Symbol.asyncIterator](){
          if(sent)return;sent=true;yield{type:'start',partial:output};await ready;
          yield{type:'text_start',contentIndex:0,partial:output};
          yield{type:'text_delta',contentIndex:0,delta:'OFFLINE_TEST_COMPLETE',partial:output};
          yield{type:'text_end',contentIndex:0,content:'OFFLINE_TEST_COMPLETE',partial:output};
          yield{type:'done',reason:'stop',message:output};
        }};
    },
  });
}
