// The daily spin wheel was replaced by Rewards (fixed daily check-in, no chance) on 25 Nov 2026.
// Old links to /spin land on Rewards.
import { Redirect } from 'expo-router';

export default function Spin() {
  return <Redirect href="/rewards" />;
}
