import React from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { MediaItem, RenderOptions } from '../types';
import { Tag } from './Tag';

export function SidebarMediaTab({
  mediaItems,
  favoriteClipIds,
  onUpload,
  onToggleFavorite,
}: {
  mediaItems: MediaItem[];
  favoriteClipIds: string[];
  onUpload: () => void;
  onToggleFavorite: (clipId: string) => void;
}) {
  return (
    <View style={styles.root}>
      {/* Upload zone */}
      <Pressable
        onPress={onUpload}
        style={({ pressed, hovered }: any) => [
          styles.uploadZone,
          hovered && styles.uploadZoneHovered,
          pressed && styles.uploadZonePressed,
        ]}
      >
        <View style={styles.uploadIcon}>
          <Ionicons name="cloud-upload-outline" size={22} color={colors.blue} />
        </View>
        <View>
          <Text style={styles.uploadTitle}>Add clips</Text>
          <Text style={styles.uploadSub}>MP4, MOV, M4V, WebM</Text>
        </View>
      </Pressable>

      {/* Clip list */}
      {mediaItems.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="videocam-outline" size={24} color={colors.subtle} />
          <Text style={styles.emptyText}>No clips uploaded yet</Text>
        </View>
      ) : (
        <View style={styles.clipList}>
          <Text style={styles.sectionLabel}>{mediaItems.length} clip{mediaItems.length !== 1 ? 's' : ''}</Text>
          {mediaItems.map((item, index) => {
            const favorite = favoriteClipIds.includes(item.id);
            const duration = item.analysis?.duration_seconds;
            const quality = item.analysis?.quality_label;
            return (
              <View key={item.id} style={styles.clipRow}>
                <View style={styles.clipThumb}>
                  <Text style={styles.clipIndex}>{index + 1}</Text>
                </View>
                <View style={styles.clipInfo}>
                  <Text style={styles.clipName} numberOfLines={1}>{item.filename}</Text>
                  <View style={styles.clipMeta}>
                    {duration != null ? <Text style={styles.clipDetail}>{Math.round(duration)}s</Text> : null}
                    {quality ? <Tag label={quality} tone={quality === 'dark' || quality === 'soft or shaky' ? 'warning' : 'neutral'} /> : null}
                  </View>
                </View>
                <Pressable onPress={() => onToggleFavorite(item.id)} style={styles.starButton}>
                  <Ionicons
                    name={favorite ? 'star' : 'star-outline'}
                    size={16}
                    color={favorite ? colors.amber : colors.subtle}
                  />
                </Pressable>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 10,
  },
  uploadZone: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.blue,
    backgroundColor: colors.surfaceRaised,
    padding: 14,
    ...(Platform.OS === 'web' ? ({ transition: 'all 150ms ease', cursor: 'pointer' } as any) : {}),
  },
  uploadZoneHovered: {
    borderColor: colors.blue,
    backgroundColor: 'rgba(0, 229, 255, 0.06)',
  },
  uploadZonePressed: {
    transform: [{ scale: 0.98 }],
  },
  uploadIcon: {
    width: 40,
    height: 40,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.blueSoft,
  },
  uploadTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: '800',
  },
  uploadSub: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '600',
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 32,
    gap: 8,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
  },
  sectionLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  clipList: {
    gap: 4,
  },
  clipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    paddingVertical: 8,
    ...(Platform.OS === 'web' ? ({ transition: 'background 120ms ease' } as any) : {}),
  },
  clipThumb: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    backgroundColor: colors.paper,
    alignItems: 'center',
    justifyContent: 'center',
  },
  clipIndex: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '900',
  },
  clipInfo: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  clipName: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: '700',
  },
  clipMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  clipDetail: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
  },
  starButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
  },
});
