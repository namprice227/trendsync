import React from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, layout } from '../theme';
import type { SidebarTab } from '../types';

const TABS: { key: SidebarTab; icon: keyof typeof Ionicons.glyphMap; label: string }[] = [
  { key: 'media', icon: 'film-outline', label: 'Media' },
  { key: 'story', icon: 'sparkles-outline', label: 'Story' },
  { key: 'intelligence', icon: 'analytics-outline', label: 'Intel' },
  { key: 'brief', icon: 'bulb-outline', label: 'Brief' },
];

export function Sidebar({
  activeTab,
  onTabChange,
  children,
}: {
  activeTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.root}>
      {/* Icon rail */}
      <View style={styles.iconRail}>
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <Pressable
              key={tab.key}
              onPress={() => onTabChange(tab.key)}
              style={({ hovered }: any) => [
                styles.tabButton,
                active && styles.tabButtonActive,
                hovered && !active && styles.tabButtonHovered,
              ]}
            >
              <Ionicons
                name={active ? (tab.icon.replace('-outline', '') as any) : tab.icon}
                size={18}
                color={active ? colors.blue : colors.muted}
              />
              <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{tab.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* Tab content */}
      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentInner}
        showsVerticalScrollIndicator={false}
      >
        {children}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    flexDirection: 'column',
  },
  iconRail: {
    flexDirection: 'row',
    paddingHorizontal: 6,
    paddingVertical: 8,
    gap: 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.paper,
  },
  tabButton: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: radii.md,
    gap: 3,
    ...(Platform.OS === 'web' ? ({ transition: 'all 150ms ease', cursor: 'pointer' } as any) : {}),
  },
  tabButtonActive: {
    backgroundColor: 'rgba(0, 229, 255, 0.12)',
  },
  tabButtonHovered: {
    backgroundColor: colors.surfaceRaised,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.muted,
    textAlign: 'center',
  },
  tabLabelActive: {
    color: colors.blue,
  },
  content: {
    flex: 1,
  },
  contentInner: {
    padding: 12,
    gap: 10,
    paddingBottom: 24,
  },
});
