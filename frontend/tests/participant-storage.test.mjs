import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('../app/participant-storage.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {loadParticipant,saveParticipant}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
function storage(){const items=new Map();return {getItem:k=>items.get(k)||null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};}
const first={session_id:'session-one',participant_id:'student-one',token:'secret-one',code:'123456'};
test('closing a tab retains identity and resolves code or original session link',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};
 saveParticipant(first);window.sessionStorage=storage();
 assert.deepEqual(loadParticipant(first.code),first);
 assert.deepEqual(loadParticipant(first.session_id),first);
 assert.deepEqual(loadParticipant(),first);
});
test('multiple quizzes retain independent credentials and unknown codes never restore another quiz',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};saveParticipant(first);
 const second={...first,code:'654321',session_id:'session-two',token:'secret-two'};saveParticipant(second);
 assert.deepEqual(loadParticipant(first.code),first);assert.deepEqual(loadParticipant(second.code),second);
 assert.equal(loadParticipant('999999'),null);
});
test('legacy tab credentials migrate to persistent storage',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};
 window.sessionStorage.setItem('quizeee-participant',JSON.stringify(first));
 assert.deepEqual(loadParticipant(first.code),first);window.sessionStorage=storage();assert.deepEqual(loadParticipant(first.code),first);
});
test('corrupt and blocked storage does not crash recovery',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};window.localStorage.setItem('quizeee-participant','broken');assert.equal(loadParticipant(),null);
 Object.defineProperty(window,'localStorage',{get(){throw Error('blocked');}});saveParticipant(first);assert.deepEqual(loadParticipant(first.code),first);
});

test('email matching never reuses another student or unverified legacy credentials',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};saveParticipant(first);
 assert.equal(loadParticipant(first.code,'new@example.com'),null);
 const identified={...first,email:'first@example.com'};saveParticipant(identified);
 assert.deepEqual(loadParticipant(first.code,' FIRST@example.com '),identified);
 assert.equal(loadParticipant(first.code,'second@example.com'),null);
});


test('two emails in the same quiz keep their own resume and dashboard credentials',()=>{
 global.window={localStorage:storage(),sessionStorage:storage()};
 const hima={...first,email:'hima@gmail.com'};
 const mollatuhina={...first,participant_id:'student-two',token:'secret-two',email:'mollatuhina@gmail.com'};
 saveParticipant(hima);saveParticipant(mollatuhina);
 assert.deepEqual(loadParticipant(first.code,hima.email),hima);
 assert.deepEqual(loadParticipant(first.code,mollatuhina.email),mollatuhina);
 assert.deepEqual(loadParticipant(hima.participant_id),hima);
 assert.deepEqual(loadParticipant(mollatuhina.participant_id),mollatuhina);
});
