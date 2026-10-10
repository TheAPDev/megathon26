import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from './client'
import { Api } from './endpoints'
import type * as T from './types'

// Errors the user cannot fix by retrying: don't retry them in the query layer either.
const noRetry = (n: number, e: unknown) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 1
const REF = { staleTime: Infinity, gcTime: Infinity, retry: noRetry }

export const keys = {
  home: (id: string) => ['home', id] as const,
  score: (id: string) => ['home', id, 'score'] as const,
  plan: (id: string) => ['home', id, 'plan'] as const,
  journey: (id: string) => ['home', id, 'journey'] as const,
}

export const useConfig = () => useQuery({ queryKey: ['config'], queryFn: Api.config, ...REF })
export const useCities = () => useQuery({ queryKey: ['ref', 'cities'], queryFn: Api.cities, ...REF })
export const useRetrofits = () => useQuery({ queryKey: ['ref', 'retrofits'], queryFn: Api.retrofits, ...REF })
export const useMyHomes = (enabled: boolean) => useQuery({ queryKey: ['me', 'homes'], queryFn: Api.myHomes, enabled, retry: noRetry })

const homeQ = <R,>(key: readonly unknown[], fn: () => Promise<R>, id: string | null, extra: object = {}) =>
  ({ queryKey: key, queryFn: fn, enabled: !!id, retry: noRetry, staleTime: 5 * 60_000, ...extra })

export const useHome = (id: string | null) => useQuery(homeQ(['home', id], () => Api.home(id!), id))
export const useScore = (id: string | null) => useQuery(homeQ(['home', id, 'score'], () => Api.score(id!), id))
export const usePlan = (id: string | null) => useQuery(homeQ(['home', id, 'plan'], () => Api.plan(id!), id))
export const useJourney = (id: string | null) => useQuery(homeQ(['home', id, 'journey'], () => Api.journey(id!), id))
export const useHeatwave = (id: string | null) => useQuery(homeQ(['home', id, 'heatwave'], () => Api.heatwave(id!), id))
export const useWeatherSignature = (id: string | null) =>
  useQuery(homeQ(['home', id, 'weather'], () => Api.weatherSignature(id!), id, { staleTime: 60 * 60_000 }))
export const useRealCity = (city: string | undefined) =>
  useQuery({ queryKey: ['real', 'city', city], queryFn: () => Api.realCity(city!), enabled: !!city, retry: noRetry, staleTime: 60 * 60_000 })

export function useScenario(id: string | null, retrofits: string[], params: Record<string, number>) {
  return useQuery({
    queryKey: ['home', id, 'scenario', retrofits.join(','), params],
    queryFn: ({ signal }) => Api.scenario(id!, { retrofits, params }, signal),
    enabled: !!id && retrofits.length > 0,
    placeholderData: keepPreviousData,
    retry: noRetry,
    staleTime: 10 * 60_000,
  })
}

export function useFinance(id: string | null, retrofits: string[], params: Record<string, number>, down: number) {
  return useQuery({
    queryKey: ['home', id, 'finance', retrofits.join(','), params, down],
    queryFn: () => Api.finance(id!, { retrofits, params, down_payment_inr: down }),
    enabled: !!id && retrofits.length > 0,
    placeholderData: keepPreviousData,
    retry: noRetry,
  })
}

export const useValue = (id: string | null, retrofits: string[]) =>
  useQuery({ queryKey: ['home', id, 'value', retrofits.join(',')], queryFn: () => Api.value(id!, retrofits), enabled: !!id, retry: noRetry, placeholderData: keepPreviousData })
export const useSolar = (id: string | null, kw?: number) =>
  useQuery({ queryKey: ['home', id, 'solar', kw ?? 'auto'], queryFn: () => Api.solar(id!, kw), enabled: !!id, retry: noRetry, placeholderData: keepPreviousData })
export const useRoadmap = (id: string | null, budget: number, years: number, objective: 'inr' | 'co2' | 'kwh') =>
  useQuery({
    queryKey: ['home', id, 'roadmap', budget, years, objective],
    queryFn: () => Api.roadmap(id!, budget, years, objective),
    enabled: !!id && budget >= 1000,
    retry: noRetry,
    placeholderData: keepPreviousData,
  })

/** Any write to a home invalidates everything derived from it (plan, score, scenarios, journey, finance). */
export function useInvalidateHome() {
  const qc = useQueryClient()
  // Cancel first: a read that started before the write would otherwise land afterwards with stale data
  // (React Query will not start a second fetch for a query that is still loading).
  return async (id: string) => {
    await qc.cancelQueries({ queryKey: ['home', id] })
    await qc.invalidateQueries({ queryKey: ['home', id] })
  }
}

export function useAddMemory(id: string | null) {
  const invalidate = useInvalidateHome()
  return useMutation({ mutationFn: (m: T.MemoryIn) => Api.addMemory(id!, m), onSuccess: () => id && invalidate(id) })
}

export function useCreateHome() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: Api.createHome,
    onSuccess: (r) => {
      qc.setQueryData(keys.score(r.home.home_id), r.score)
      qc.setQueryData(['home', r.home.home_id], r.home)
      qc.invalidateQueries({ queryKey: ['me', 'homes'] })
    },
  })
}
