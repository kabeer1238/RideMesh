import com.bikemesh.ridemesh.mesh.MeshRelayPolicy;
import com.bikemesh.ridemesh.offline.FreshAudioQueue;
import java.util.*;

public class OfflinePolicyCheck {
    static void check(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    static Set<Integer> flood(int source, boolean ring, int missing) {
        Set<Integer> seen = new HashSet<>(); seen.add(source);
        ArrayDeque<int[]> q = new ArrayDeque<>(); q.add(new int[]{source, 5});
        while (!q.isEmpty()) {
            int[] p = q.remove(); if (p[1] == 0) continue;
            for (int n=1;n<=6;n++) {
                boolean linked=MeshRelayPolicy.allows(p[0],n)||(ring&&Math.abs(p[0]-n)==5);
                if (!linked||n==missing||!seen.add(n)) continue;
                if (MeshRelayPolicy.shouldForward(p[1]-1,true)) q.add(new int[]{n,p[1]-1});
            }
        }
        return seen;
    }
    public static void main(String[] args) {
        for (int s=1;s<=6;s++) {
            check(flood(s,false,-1).size()==6,"chain source "+s);
            check(flood(s,true,-1).size()==6,"ring source "+s);
        }
        check(flood(1,false,3).equals(Set.of(1,2)),"broken chain");
        check(flood(1,true,3).size()==5,"alternate route");
        check(!MeshRelayPolicy.shouldForward(0,true),"TTL exhausted");
        for (int n=1;n<=6;n++) check(!MeshRelayPolicy.allows(0,n)&&!MeshRelayPolicy.allows(n,0),"lab isolation");
        FreshAudioQueue q=new FreshAudioQueue();
        q.offer("A",new byte[]{1},0); q.offer("B",new byte[]{2},1); q.offer("A",new byte[]{3},2);
        check(q.size()==2&&q.droppedCount()==1,"latest per speaker");
        check(q.poll(10)[0]==3&&q.poll(10)[0]==2,"speaker fairness");
        q.offer("A",new byte[]{4},0); check(q.poll(141)==null,"stale frame rejection");
        for(int n=0;n<100;n++)q.offer("source"+n,new byte[]{1},200);
        check(q.size()==8,"bounded source queue");
        System.out.println("PASS: 6-source chain/ring, partition, alternate route, TTL, lab isolation, per-speaker fairness, stale frames, bounded queue");
    }
}
