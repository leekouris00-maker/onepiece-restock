import React from 'react';
import { Tabs } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { F, useTheme } from '../../src/theme';

export default function TabsLayout() {
  const c = useTheme();
  const icon = name => ({ color, size }) => <Ionicons name={name} color={color} size={size - 2} />;
  return (
    <Tabs screenOptions={{
      headerStyle: { backgroundColor: c.band }, headerTintColor: '#fff', headerShadowVisible: false,
      headerTitleStyle: { fontFamily: F.serif, fontSize: 21 },
      tabBarActiveTintColor: c.red, tabBarInactiveTintColor: c.mute,
      tabBarStyle: { backgroundColor: c.panel, borderTopColor: c.line },
      tabBarLabelStyle: { fontFamily: F.medium, fontSize: 11 },
      sceneStyle: { backgroundColor: c.bg },
    }}>
      <Tabs.Screen name="index" options={{ title: 'Collection', headerTitle: 'My collection', tabBarIcon: icon('albums-outline') }} />
      <Tabs.Screen name="market" options={{ title: 'Market', headerTitle: 'One Piece Market', tabBarIcon: icon('pricetags-outline') }} />
      <Tabs.Screen name="search" options={{ title: 'Search', tabBarIcon: icon('search-outline') }} />
      <Tabs.Screen name="account" options={{ title: 'Account', tabBarIcon: icon('person-circle-outline') }} />
    </Tabs>
  );
}
