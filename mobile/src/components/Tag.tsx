import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';


export function Tag({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'info' | 'success' | 'warning' }) {
  return (
    <View style={[styles.tag, tone === 'info' && styles.tagInfo, tone === 'success' && styles.tagSuccess, tone === 'warning' && styles.tagWarning]}>
      <Text style={[styles.tagText, tone === 'info' && styles.tagTextInfo, tone === 'success' && styles.tagTextSuccess, tone === 'warning' && styles.tagTextWarning]}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    minHeight: 26,
    borderRadius: radii.round,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 9,
    justifyContent: 'center',
  },
  tagInfo: {
    borderColor: '#c4dde2',
    backgroundColor: colors.blueSoft,
  },
  tagSuccess: {
    borderColor: '#c5ddcb',
    backgroundColor: colors.greenSoft,
  },
  tagWarning: {
    borderColor: '#ead4b5',
    backgroundColor: colors.amberSoft,
  },
  tagText: {
    color: colors.graphite,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
  },
  tagTextInfo: {
    color: colors.blueDark,
  },
  tagTextSuccess: {
    color: colors.green,
  },
  tagTextWarning: {
    color: colors.amber,
  },
});
