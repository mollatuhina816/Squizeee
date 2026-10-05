type State={revision:number;active_index:number;answered?:boolean;state?:string};
export function mergeParticipantState<T extends State>(old:T|null,next:T):T {
  if(old&&(old.revision>next.revision||old.active_index>next.active_index||old.state==='ended'&&next.state!=='ended'))return old;
  const same=old?.active_index===next.active_index;
  return {...next,answered:same?Boolean(old?.answered||next.answered):Boolean(next.answered)};
}
