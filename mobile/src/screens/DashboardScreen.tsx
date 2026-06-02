import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary, ProjectFilter, ProjectSort, ProjectAction } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { projectFilters, projectSorts, projectTitle, sessionTitle, phaseLabel, phaseFilter, phaseTone, formatUpdatedAt } from "../utils/helpers";
import { PrimaryButton } from "../components/PrimaryButton";
import { SectionHeader } from "../components/SectionHeader";
import { Tag } from "../components/Tag";
import { ProjectActionButton } from "../components/ProjectActionButton";

export function DashboardScreen({
  projects,
  loading,
  creating,
  onOpen,
  onNew,
  onRename,
  onDuplicate,
  onDelete,
  onShare,
}: {
  projects: ProjectSummary[];
  loading: boolean;
  creating: boolean;
  onOpen: (sessionId: string) => void;
  onNew: () => void;
  onRename: (sessionId: string, title: string) => Promise<void>;
  onDuplicate: (sessionId: string) => Promise<TripSession>;
  onDelete: (sessionId: string) => Promise<void>;
  onShare: (sessionId: string) => Promise<string>;
}) {
  const { width } = useWindowDimensions();
  const compact = width < 860;
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ProjectFilter>('all');
  const [sort, setSort] = useState<ProjectSort>('recent');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [action, setAction] = useState<{ id: string; type: ProjectAction } | null>(null);

  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const statusOrder: Record<TripPhase, number> = {
      collecting_context: 0,
      uploading: 0,
      ready_to_plan: 1,
      ready_to_render: 1,
      planning: 2,
      rendering: 2,
      complete: 3,
      error: 4,
    };
    return [...projects]
      .filter((project) => {
        if (filter !== 'all' && phaseFilter(project.phase) !== filter) return false;
        if (!normalizedQuery) return true;
        return `${projectTitle(project)} ${project.destination}`.toLowerCase().includes(normalizedQuery);
      })
      .sort((left, right) => {
        if (sort === 'name') return projectTitle(left).localeCompare(projectTitle(right));
        if (sort === 'status') return statusOrder[left.phase] - statusOrder[right.phase] || right.updated_at - left.updated_at;
        return right.updated_at - left.updated_at;
      });
  }, [filter, projects, query, sort]);

  const busy = Boolean(action) || creating;

  const startRename = (project: ProjectSummary) => {
    setNotice(null);
    setConfirmDeleteId(null);
    setRenamingId(project.id);
    setRenameDraft(projectTitle(project));
  };

  const commitRename = async (project: ProjectSummary) => {
    const nextTitle = renameDraft.trim();
    if (!nextTitle || nextTitle === projectTitle(project)) {
      setRenamingId(null);
      return;
    }
    setAction({ id: project.id, type: 'rename' });
    try {
      await onRename(project.id, nextTitle);
      setRenamingId(null);
      setNotice(`Renamed to ${nextTitle}`);
    } catch (renameError) {
      setNotice(renameError instanceof Error ? renameError.message : 'Rename failed');
    } finally {
      setAction(null);
    }
  };

  const duplicateProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'duplicate' });
    setNotice(null);
    try {
      const duplicate = await onDuplicate(project.id);
      setNotice(`Duplicated as ${sessionTitle(duplicate)}`);
    } catch (duplicateError) {
      setNotice(duplicateError instanceof Error ? duplicateError.message : 'Duplicate failed');
    } finally {
      setAction(null);
    }
  };

  const deleteProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'delete' });
    setNotice(null);
    try {
      await onDelete(project.id);
      setConfirmDeleteId(null);
      setNotice(`${projectTitle(project)} deleted`);
    } catch (deleteError) {
      setNotice(deleteError instanceof Error ? deleteError.message : 'Delete failed');
    } finally {
      setAction(null);
    }
  };

  const shareProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'share' });
    setNotice(null);
    try {
      const url = await onShare(project.id);
      setNotice(`Share link: ${url}`);
    } catch (shareError) {
      setNotice(shareError instanceof Error ? shareError.message : 'Share failed');
    } finally {
      setAction(null);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.dashboardScreen}>
      <View style={styles.dashboardBand}>
        <View style={[styles.dashboardHeader, compact && styles.dashboardHeaderCompact]}>
          <SectionHeader icon="albums-outline" title="Projects" meta={`${projects.length} saved`} />
          <PrimaryButton icon={creating ? 'hourglass-outline' : 'add-circle-outline'} label={creating ? 'Creating' : 'New project'} onPress={onNew} disabled={busy} />
        </View>

        <View style={[styles.dashboardToolbar, compact && styles.dashboardToolbarCompact]}>
          <View style={styles.searchBox}>
            <Ionicons name="search-outline" size={16} color={colors.muted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search destination or title"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
            />
          </View>
          <View style={styles.segmentGroup}>
            {projectFilters.map((item) => {
              const active = filter === item.key;
              return (
                <Pressable key={item.key} onPress={() => setFilter(item.key)} style={[styles.segmentChip, active && styles.segmentChipActive]}>
                  <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{item.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={styles.segmentGroup}>
            {projectSorts.map((item) => {
              const active = sort === item.key;
              return (
                <Pressable key={item.key} onPress={() => setSort(item.key)} style={[styles.segmentChip, active && styles.segmentChipActive]}>
                  <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{item.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {notice ? (
          <View style={styles.dashboardNotice}>
            <Ionicons name="information-circle-outline" size={16} color={colors.blue} />
            <Text style={styles.dashboardNoticeText}>{notice}</Text>
          </View>
        ) : null}

        {loading && !projects.length ? (
          <View style={styles.projectList}>
            {[0, 1, 2].map((item) => (
              <View key={item} style={styles.projectSkeletonRow}>
                <View style={styles.skeletonTitle} />
                <View style={styles.skeletonMeta} />
              </View>
            ))}
          </View>
        ) : null}

        {!loading && !projects.length ? (
          <View style={styles.dashboardEmpty}>
            <Ionicons name="folder-open-outline" size={28} color={colors.subtle} />
            <Text style={styles.emptyText}>No projects yet. Create a project to start a TripStory workflow.</Text>
          </View>
        ) : null}

        {!loading && projects.length > 0 && !visibleProjects.length ? (
          <View style={styles.dashboardEmpty}>
            <Ionicons name="funnel-outline" size={24} color={colors.subtle} />
            <Text style={styles.emptyText}>No projects match the current search and filters.</Text>
          </View>
        ) : null}

        {visibleProjects.length ? (
          <View style={styles.projectList}>
            {visibleProjects.map((project) => {
              const title = projectTitle(project);
              const rowAction = (type: ProjectAction) => action?.id === project.id && action.type === type;
              return (
                <View key={project.id} style={[styles.dashboardProjectRow, compact && styles.dashboardProjectRowCompact]}>
                  <View style={styles.dashboardProjectMain}>
                    {renamingId === project.id ? (
                      <View style={styles.renameRow}>
                        <TextInput
                          value={renameDraft}
                          onChangeText={setRenameDraft}
                          autoFocus
                          onSubmitEditing={() => commitRename(project)}
                          placeholder="Project title"
                          placeholderTextColor={colors.muted}
                          style={[styles.input, styles.renameInput]}
                        />
                        <ProjectActionButton icon="checkmark" label="Save rename" onPress={() => commitRename(project)} busy={rowAction('rename')} disabled={busy && !rowAction('rename')} />
                        <ProjectActionButton icon="close" label="Cancel rename" onPress={() => setRenamingId(null)} disabled={busy} />
                      </View>
                    ) : (
                      <Pressable onPress={() => onOpen(project.id)} disabled={busy} style={styles.projectOpenTarget}>
                        <Text style={styles.dashboardProjectTitle}>{title}</Text>
                        <Text style={styles.dashboardProjectSubtitle}>{project.destination}</Text>
                      </Pressable>
                    )}
                  </View>

                  <View style={styles.projectFacts}>
                    <Tag label={phaseLabel(project.phase)} tone={phaseTone(project.phase)} />
                    <View style={styles.projectFact}>
                      <Ionicons name="videocam-outline" size={14} color={colors.muted} />
                      <Text style={styles.projectFactText}>{project.media_count}</Text>
                    </View>
                    <Tag label={project.final_video_url ? 'Render ready' : 'No render'} tone={project.final_video_url ? 'success' : 'neutral'} />
                    <Tag label={project.share_token ? 'Shared' : 'Private'} tone={project.share_token ? 'info' : 'neutral'} />
                    <View style={styles.projectFact}>
                      <Ionicons name="time-outline" size={14} color={colors.muted} />
                      <Text style={styles.projectFactText}>{formatUpdatedAt(project.updated_at)}</Text>
                    </View>
                  </View>

                  {confirmDeleteId === project.id ? (
                    <View style={styles.deleteConfirmRow}>
                      <Text style={styles.deleteConfirmText}>Delete permanently?</Text>
                      <Pressable onPress={() => setConfirmDeleteId(null)} disabled={busy} style={styles.confirmButton}>
                        <Text style={styles.confirmButtonText}>Cancel</Text>
                      </Pressable>
                      <Pressable onPress={() => deleteProject(project)} disabled={busy} style={[styles.confirmButton, styles.confirmButtonDanger]}>
                        {rowAction('delete') ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={[styles.confirmButtonText, styles.confirmButtonTextDanger]}>Delete</Text>}
                      </Pressable>
                    </View>
                  ) : (
                    <View style={styles.projectActions}>
                      <ProjectActionButton icon="open-outline" label="Open project" onPress={() => onOpen(project.id)} disabled={busy} />
                      <ProjectActionButton icon="create-outline" label="Rename project" onPress={() => startRename(project)} disabled={busy} />
                      <ProjectActionButton icon="copy-outline" label="Duplicate project" onPress={() => duplicateProject(project)} busy={rowAction('duplicate')} disabled={busy && !rowAction('duplicate')} />
                      <ProjectActionButton icon="share-outline" label="Share project" onPress={() => shareProject(project)} busy={rowAction('share')} disabled={busy && !rowAction('share')} />
                      <ProjectActionButton icon="trash-outline" label="Delete project" onPress={() => setConfirmDeleteId(project.id)} disabled={busy} danger />
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  dashboardScreen: {
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 14,
    paddingBottom: 34,
  },
  dashboardBand: {
    width: '100%',
    maxWidth: 1180,
    alignSelf: 'center',
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    padding: 16,
    gap: 14,
  },
  dashboardHeader: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  dashboardHeaderCompact: {
    alignItems: 'stretch',
    flexDirection: 'column',
  },
  dashboardToolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  dashboardToolbarCompact: {
    alignItems: 'stretch',
  },
  searchBox: {
    minHeight: 42,
    minWidth: 240,
    flexGrow: 1,
    flexBasis: 280,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
  },
  searchInput: {
    flex: 1,
    minHeight: 40,
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '700',
  },
  segmentGroup: {
    minHeight: 42,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    padding: 3,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 3,
  },
  segmentChip: {
    minHeight: 34,
    borderRadius: radii.sm,
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  segmentChipActive: {
    backgroundColor: colors.blue,
  },
  segmentText: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  segmentTextActive: {
    color: colors.white,
  },
  dashboardNotice: {
    minHeight: 40,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: '#c4dde2',
    backgroundColor: colors.blueSoft,
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dashboardNoticeText: {
    flex: 1,
    color: colors.blueDark,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '800',
  },
  projectList: {
    gap: 8,
  },
  projectSkeletonRow: {
    minHeight: 74,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    padding: 14,
    gap: 10,
  },
  skeletonTitle: {
    width: '42%',
    height: 14,
    borderRadius: radii.sm,
    backgroundColor: colors.mist,
  },
  skeletonMeta: {
    width: '68%',
    height: 12,
    borderRadius: radii.sm,
    backgroundColor: colors.mist,
  },
  dashboardEmpty: {
    minHeight: 146,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: 18,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  dashboardProjectRow: {
    minHeight: 76,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  dashboardProjectRowCompact: {
    alignItems: 'stretch',
    flexDirection: 'column',
  },
  dashboardProjectMain: {
    flex: 1.2,
    minWidth: 220,
  },
  renameRow: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  input: {
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.ink,
    fontSize: 14,
    fontWeight: '700',
    backgroundColor: colors.surfaceRaised,
  },
  renameInput: {
    flex: 1,
    minHeight: 42,
  },
  projectOpenTarget: {
    minHeight: 48,
    justifyContent: 'center',
    gap: 3,
  },
  dashboardProjectTitle: {
    color: colors.ink,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  dashboardProjectSubtitle: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  projectFacts: {
    flex: 1,
    minWidth: 260,
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 7,
  },
  projectFact: {
    minHeight: 26,
    borderRadius: radii.round,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  projectFactText: {
    color: colors.graphite,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
  },
  deleteConfirmRow: {
    minWidth: 260,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
  },
  deleteConfirmText: {
    color: colors.red,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  confirmButton: {
    minHeight: 34,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  confirmButtonText: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  confirmButtonDanger: {
    minWidth: 72,
    borderColor: colors.red,
    backgroundColor: colors.red,
  },
  confirmButtonTextDanger: {
    color: colors.white,
  },
  projectActions: {
    minWidth: 196,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 6,
  },
});
