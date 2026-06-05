import React from 'react';
import { View, StyleSheet, useWindowDimensions, Platform } from 'react-native';
import { colors, layout } from '../theme';

export function EditorLayout({
  sidebar,
  center,
  timeline,
  properties,
}: {
  sidebar: React.ReactNode;
  center: React.ReactNode;
  timeline: React.ReactNode;
  properties: React.ReactNode;
}) {
  const { width, height } = useWindowDimensions();
  const isDesktop = width >= layout.desktopMin;

  if (!isDesktop) {
    // Tablet / mobile: stack vertically, no fixed sidebar
    return (
      <View style={styles.mobileRoot}>
        <View style={styles.mobileCenter}>{center}</View>
        <View style={styles.mobileTimeline}>{timeline}</View>
        <View style={styles.mobileProperties}>{properties}</View>
        <View style={styles.mobileSidebar}>{sidebar}</View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Left sidebar */}
      <View style={styles.sidebar}>{sidebar}</View>

      {/* Center: preview on top, timeline on bottom */}
      <View style={styles.centerColumn}>
        <View style={styles.preview}>{center}</View>
        <View style={styles.timeline}>{timeline}</View>
      </View>

      {/* Right properties panel */}
      <View style={styles.properties}>{properties}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: colors.paper,
    overflow: 'hidden',
  },

  // --- Desktop sidebar ---
  sidebar: {
    width: layout.sidebarExpanded,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.line,
    ...(Platform.OS === 'web'
      ? ({ overflowY: 'auto', overflowX: 'hidden' } as any)
      : {}),
  },

  // --- Desktop center column ---
  centerColumn: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'column',
  },
  preview: {
    flex: 1,
    minHeight: 0,
  },
  timeline: {
    height: layout.timelineHeight,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },

  // --- Desktop right properties ---
  properties: {
    width: layout.propertiesWidth,
    backgroundColor: colors.surface,
    borderLeftWidth: 1,
    borderLeftColor: colors.line,
    ...(Platform.OS === 'web'
      ? ({ overflowY: 'auto', overflowX: 'hidden' } as any)
      : {}),
  },

  // --- Mobile / tablet stacked layout ---
  mobileRoot: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  mobileCenter: {
    height: 280,
  },
  mobileTimeline: {
    height: 180,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },
  mobileProperties: {
    flex: 1,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  mobileSidebar: {
    height: 52,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
});
