import {
  AirVent, BatteryCharging, Blinds, CookingPot, Droplets, Fan, Gauge, Home, Layers, Lightbulb, Plug, Refrigerator,
  ShowerHead, SlidersHorizontal, Sun, SunMedium, ThermometerSun, Wind, Zap, type LucideIcon,
} from 'lucide-react'

export const RETROFIT_ICON: Record<string, LucideIcon> = {
  cool_roof: SunMedium,
  roof_insulation: Layers,
  external_shading: Blinds,
  solar_film: Sun,
  ac_setpoint: ThermometerSun,
  smart_plug_tod: Plug,
  ac_5star_inverter: AirVent,
  bldc_fans: Fan,
  led_lighting: Lightbulb,
  fridge_5star: Refrigerator,
  solar_water_heater: ShowerHead,
  heat_pump_geyser: Droplets,
  induction_cooking: CookingPot,
  lithium_battery: BatteryCharging,
  rooftop_solar: Zap,
}
export const retrofitIcon = (id: string) => RETROFIT_ICON[id] ?? SlidersHorizontal

export const COMPONENT_ICON: Record<string, LucideIcon> = {
  energy_efficiency: Gauge,
  consumption_intensity: Zap,
  envelope: Home,
  cooling_system: AirVent,
  windows_shading: Blinds,
  renewables: Sun,
  smart_use: Wind,
}
