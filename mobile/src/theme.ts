import { ViewStyle } from 'react-native';

export const colors = {
  // Base Backgrounds (Deep Slate/Indigo)
  paper: '#0A0D14', // The deepest background (main app background)
  surface: '#131824', // Cards, panels, sidebars
  surfaceRaised: '#1E2536', // Modals, elevated cards, dropdowns

  // Glassmorphism surfaces
  glass: 'rgba(19, 24, 36, 0.85)',
  glassLight: 'rgba(30, 37, 54, 0.72)',
  glassBorder: 'rgba(255, 255, 255, 0.06)',

  // Text / Typography
  ink: '#FFFFFF', // Primary text
  graphite: '#E2E8F0', // Secondary text
  muted: '#94A3B8', // Placeholder, muted text
  subtle: '#64748B', // Icons, extremely muted

  // Borders
  line: '#1E2536',
  lineStrong: '#334155',

  // Accents (Electric Cyan & Neon Violet)
  blue: '#00E5FF', // Primary action color
  blueDark: '#00B8D9', // Hover/Pressed state
  blueSoft: 'rgba(0, 229, 255, 0.1)', // Tints for tags/active backgrounds

  violet: '#B000FF',
  violetSoft: 'rgba(176, 0, 255, 0.1)',

  // Gradient accent pairs
  gradientStart: '#00E5FF',
  gradientEnd: '#B000FF',

  // Status Colors (Dark mode optimized)
  green: '#10B981',
  greenSoft: 'rgba(16, 185, 129, 0.1)',
  amber: '#F59E0B',
  amberSoft: 'rgba(245, 158, 11, 0.1)',
  red: '#EF4444',
  redSoft: 'rgba(239, 68, 68, 0.1)',

  // Legacy mappings for backwards compatibility while migrating
  coral: '#EF4444',
  white: '#FFFFFF',
  mist: '#1E2536',
  camera: '#000000',
  cameraPanel: 'rgba(0,0,0,0.8)',
};

export const radii = {
  xs: 4,
  sm: 6,
  md: 10,
  lg: 16,
  xl: 20,
  round: 999,
};

export const shadow: ViewStyle = {
  shadowColor: '#000000',
  shadowOpacity: 0.3,
  shadowRadius: 20,
  shadowOffset: { width: 0, height: 8 },
  elevation: 5,
};

export const shadowSubtle: ViewStyle = {
  shadowColor: '#000000',
  shadowOpacity: 0.15,
  shadowRadius: 8,
  shadowOffset: { width: 0, height: 2 },
  elevation: 2,
};

export const timing = {
  quick: 150,
  base: 250,
  smooth: 400,
};

// --- CapCut-style layout dimensions ---
export const layout = {
  // Top bar
  topBarHeight: 52,

  // Left sidebar
  sidebarCollapsed: 52,
  sidebarExpanded: 260,

  // Right properties panel
  propertiesWidth: 320,

  // Bottom timeline
  timelineHeight: 240,

  // Breakpoints
  desktopMin: 1024,
  tabletMin: 768,
};
