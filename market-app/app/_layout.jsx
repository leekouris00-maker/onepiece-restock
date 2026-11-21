import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { Lato_400Regular, Lato_700Bold, Lato_900Black } from '@expo-google-fonts/lato';
import { Oswald_500Medium, Oswald_700Bold } from '@expo-google-fonts/oswald';
import { DataProvider } from '../src/data';
import { F, useTheme } from '../src/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function Root() {
  const [loaded] = useFonts({ Lato_400Regular, Lato_700Bold, Lato_900Black, Oswald_500Medium, Oswald_700Bold });
  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  if (!loaded) return null;
  return <DataProvider><Nav /></DataProvider>;
}

function Nav() {
  const c = useTheme();
  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: c.bg }, headerTintColor: c.ink, headerShadowVisible: false,
        headerTitleStyle: { fontFamily: F.head, fontSize: 19, letterSpacing: 0.6 }, headerBackTitle: 'Back', contentStyle: { backgroundColor: c.bg },
      }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="set/[id]" options={{ title: '' }} />
        <Stack.Screen name="card/[k]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="item/[id]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="addcard" options={{ title: 'Add a card', presentation: 'modal' }} />
        <Stack.Screen name="movers" options={{ title: 'Market movers' }} />
      </Stack>
    </>
  );
}
