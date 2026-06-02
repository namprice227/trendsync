import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { LLM_PROVIDERS } from "../utils/helpers";

export function ProviderPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <View style={styles.providerGrid}>
      {LLM_PROVIDERS.map((provider) => {
        const active = value === provider.code;
        return (
          <Pressable
            key={provider.code}
            onPress={() => onChange(provider.code)}
            style={[styles.providerCard, active && styles.providerCardActive]}
          >
            <View style={[styles.providerIcon, active && styles.providerIconActive]}>
              <Ionicons name={active ? 'checkmark' : 'key-outline'} size={15} color={active ? colors.white : colors.blue} />
            </View>
            <View style={styles.providerCopy}>
              <Text style={[styles.providerName, active && styles.providerNameActive]}>{provider.label}</Text>
              <Text style={[styles.providerDetail, active && styles.providerDetailActive]}>{provider.detail}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  providerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  providerCard: {
    minHeight: 66,
    flexGrow: 1,
    flexBasis: 160,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  providerCardActive: {
    borderColor: colors.blue,
    backgroundColor: colors.blueSoft,
  },
  providerIcon: {
    width: 30,
    height: 30,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.mist,
  },
  providerIconActive: {
    backgroundColor: colors.blue,
  },
  providerCopy: {
    flex: 1,
  },
  providerName: {
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  providerNameActive: {
    color: colors.ink,
  },
  providerDetail: {
    marginTop: 2,
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  providerDetailActive: {
    color: colors.graphite,
  },
});
