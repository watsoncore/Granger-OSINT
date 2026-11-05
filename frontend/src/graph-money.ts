/** Decimal strings stay decimal strings; graph labels must not lose token units. */
type DecimalParts={negative:boolean;digits:string;places:number}
function parts(value:unknown):DecimalParts|undefined{
  if(typeof value!=='string'&&typeof value!=='number')return
  const text=String(value).trim(),match=/^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(text)
  if(!match)return
  const exponent=Number(match[4]||0)
  if(!Number.isInteger(exponent)||Math.abs(exponent)>200)return
  let digits=(match[2]+(match[3]||'')).replace(/^0+/,'')||'0',places=(match[3]||'').length-exponent
  if(places<0){digits+='0'.repeat(-places);places=0}
  while(places&&digits.endsWith('0')){digits=digits.slice(0,-1)||'0';places--}
  return {negative:match[1]==='-'&&digits!=='0',digits,places}
}
function decimal(value:DecimalParts){
  const {digits,places}=value,padded=digits.padStart(places+1,'0')
  return (value.negative?'-':'')+(places?padded.slice(0,-places)+'.'+padded.slice(-places):digits)
}
export function exactGraphAmount(value:unknown):string{
  const parsed=parts(value)
  return parsed?decimal(parsed):'Неизвестно'
}
export function addGraphAmounts(values:unknown[]):string|null{
  const parsed=values.map(parts)
  if(!parsed.length||parsed.some(value=>!value))return null
  const places=Math.max(...parsed.map(value=>value!.places))
  const total=parsed.reduce((sum,value)=>sum+BigInt((value!.negative?'-':'')+value!.digits)*10n**BigInt(places-value!.places),0n)
  const digits=(total<0n?-total:total).toString().padStart(places+1,'0')
  return exactGraphAmount((total<0n?'-':'')+(places?digits.slice(0,-places)+'.'+digits.slice(-places):digits))
}
export function formatGraphAmount(value:unknown,compact=true):string{
  const parsed=parts(value)
  if(!parsed)return 'Неизвестно'
  const exact=decimal(parsed)
  if(!compact||parsed.digits==='0')return exact
  const sign=parsed.negative?'-':'',power=parsed.digits.length-parsed.places-1
  // Tiny nonzero transfers remain nonzero, with an explicit exponent.
  if(power<=-6||power>=15){const significant=parsed.digits.slice(0,4).replace(/0+$/,'');return sign+significant[0]+(significant.length>1?'.'+significant.slice(1):'')+'e'+(power>=0?'+':'')+power}
  for(const [threshold,suffix] of [[12,'T'],[9,'B'],[6,'M'],[3,'K']] as const){
    if(power>=threshold){const shifted=decimal({...parsed,negative:false,places:parsed.places+threshold}),[whole,fraction='']=shifted.split('.'),shown=fraction.slice(0,2).replace(/0+$/,'');return sign+whole+(shown?'.'+shown:'')+suffix}
  }
  const [whole,fraction='']=exact.split('.')
  if(fraction.length<=6)return exact
  const significant=fraction.search(/[1-9]/),keep=Math.max(4,significant+3)
  return whole+'.'+fraction.slice(0,keep).replace(/0+$/,'')+'…'
}
