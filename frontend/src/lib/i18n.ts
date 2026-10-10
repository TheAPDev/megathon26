import { useSession, type Lang } from '../state/session'

// Interface chrome in English and Hindi. Engine text (reasons, advice) comes from the backend in English;
// the AI Saathi answers in the user's language.
const dict = {
  dashboard: ['Dashboard', 'डैशबोर्ड'],
  billToScore: ['Bill to score', 'बिल से स्कोर'],
  studio: ['Retrofit studio', 'रेट्रोफिट स्टूडियो'],
  paisa: ['Paisa: value & finance', 'पैसा: मूल्य और फाइनेंस'],
  saathi: ['AI Saathi', 'AI साथी'],
  garmi: ['Garmi mode', 'गर्मी मोड'],
  portfolio: ['Lender portfolio', 'ऋणदाता पोर्टफोलियो'],
  forLenders: ['For lenders', 'ऋणदाताओं के लिए'],
  myHome: ['My home', 'मेरा घर'],
  yourScore: ['Your Green Ghar Score', 'आपका ग्रीन घर स्कोर'],
  breakdown: ['Score breakdown', 'स्कोर का विवरण'],
  nextAction: ['Next best action', 'अगला सबसे अच्छा कदम'],
  usage: ['Electricity use', 'बिजली की खपत'],
  signOut: ['Sign out', 'साइन आउट'],
  signIn: ['Sign in', 'साइन इन'],
  switchHome: ['Switch home', 'घर बदलें'],
  addHome: ['Add a home', 'घर जोड़ें'],
} satisfies Record<string, [string, string]>

export type Key = keyof typeof dict
export const t = (k: Key, lang: Lang) => dict[k][lang === 'hi' ? 1 : 0]
export function useT() {
  const lang = useSession((s) => s.language)
  return (k: Key) => t(k, lang)
}
