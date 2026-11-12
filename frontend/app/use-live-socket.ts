'use client';
import { authFetch } from './auth-fetch';
import { useEffect, useRef, useState } from 'react';
import { readApiResponse } from './api-response';
export function useLiveSocket<T>(ticketUrl:string|null, token:string|undefined, onSnapshot:(data:T)=>void, recover:()=>void, onEvent?:(event:{type:string;id:string;emoji?:string;nickname?:string;participant_id?:string})=>void) {
  const [connection,setConnection]=useState('Connecting');
  const handlers=useRef({onSnapshot,recover,onEvent});handlers.current={onSnapshot,recover,onEvent};
  useEffect(()=>{
    if(!ticketUrl)return;
    let stopped=false;let socket:WebSocket|undefined;let retry:ReturnType<typeof setTimeout>;
    async function connect(){
      setConnection('Connecting');
      try{
        const response=await (token ? fetch : authFetch)(ticketUrl!,{method:'POST',headers:token?{'X-Participant-Token':token}:{}});
        const {ticket}=await readApiResponse<{ticket:string}>(response);
        if(stopped)return;
        const origin=process.env.NEXT_PUBLIC_WS_ORIGIN||`${location.protocol==='https:'?'wss':'ws'}://${location.hostname}:8000`;
        socket=new WebSocket(`${origin}/api/v1/live/ws`);
        socket.onopen=()=>socket?.send(ticket);
        socket.onmessage=event=>{try{const message=JSON.parse(event.data);
          if(message.type==='ready'){setConnection('Live');handlers.current.recover();}
          if(message.type==='snapshot.changed'&&message.snapshot){setConnection('Live');handlers.current.onSnapshot(message.snapshot);}
          if(message.type==='reaction'||message.type==='picker')handlers.current.onEvent?.(message);
        }catch{handlers.current.recover();}};
        socket.onclose=()=>{if(!stopped){setConnection('Reconnecting');retry=setTimeout(connect,1000);}};
        socket.onerror=()=>socket?.close();
      }catch{if(!stopped){setConnection('Reconnecting');retry=setTimeout(connect,3000);}}
    }
    connect();return()=>{stopped=true;clearTimeout(retry);socket?.close();};
  },[ticketUrl,token]);return connection;
}
